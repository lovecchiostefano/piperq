import io
import re
import zipfile
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Commissioni partner', layout='wide')
st.title('Calcolo commissioni partner')
st.caption('Commissioni Avanzato e monitoraggio Bonus Churn basati su attivazione e Closing Date.')

DEFAULT_COMPETENCE = pd.Timestamp('2026-09-01')


def norm(v):
    if pd.isna(v):
        return ''
    return re.sub(r'[^a-z0-9]+', '', str(v).strip().lower())


def month(v):
    if pd.isna(v):
        return pd.NaT
    return pd.Timestamp(v).to_period('M').to_timestamp()


def parse_dates(s):
    return pd.to_datetime(s, dayfirst=True, errors='coerce')


def split_ids(v):
    if pd.isna(v):
        return []
    return [x.strip() for x in str(v).split(',') if x.strip()]


def parse_decorrenza(v):
    if pd.isna(v):
        return pd.NaT
    if str(v).strip().lower() == 'no':
        return pd.NaT
    return month(pd.to_datetime(v, dayfirst=True, errors='coerce'))


def contains_promo(value, identifiers):
    n = norm(value)
    return any(norm(token) and norm(token) in n for token in identifiers)


def matches_subchannel(value, identifiers):
    n = norm(value)
    return any(norm(token) == n for token in identifiers)


def configuration_candidates(row, configs):
    sub_n = norm(row.get('Subchannel'))
    promo_n = norm(row.get('Promo code'))

    # Eccezione nota: bug Promo code, prevale Facile-B2C.
    if sub_n == norm('Facile-B2C') and promo_n == norm('Switcho!NeN'):
        return configs[configs['Sub IDs'].apply(lambda ids: matches_subchannel('Facile-B2C', ids))].copy(), 'ECCEZIONE_FACILE_PROMO_ERRATO'

    # Eccezione nota: Billoo!NeN non attribuisce Billoo con Web o NeN-B2C.
    if sub_n in {norm('Web'), norm('NeN-B2C')} and promo_n == norm('Billoo!NeN'):
        return configs.iloc[0:0].copy(), 'NON_MAPPATO_BILLOO_PROMO_NON_SUFFICIENTE'

    sub_hits = configs[configs['Sub IDs'].apply(lambda ids: matches_subchannel(row.get('Subchannel'), ids))]
    promo_hits = configs[configs['Promo IDs'].apply(lambda ids: contains_promo(row.get('Promo code'), ids))]

    # Se entrambi i criteri trovano configurazioni commerciali diverse, blocca il record.
    if not sub_hits.empty and not promo_hits.empty:
        sub_gruppi = set(sub_hits['Gruppo mapping'])
        promo_gruppi = set(promo_hits['Gruppo mapping'])
        if sub_gruppi.isdisjoint(promo_gruppi):
            return configs.iloc[0:0].copy(), 'CONFLITTO_SUBCHANNEL_PROMO'
        hits = pd.concat([sub_hits, promo_hits]).drop_duplicates(subset=['Agente', 'Decorrenza'])
        return hits, 'SUBCHANNEL+PROMO'
    if not sub_hits.empty:
        return sub_hits.copy(), 'SUBCHANNEL'
    if not promo_hits.empty:
        return promo_hits.copy(), 'PROMO'
    return configs.iloc[0:0].copy(), 'NON_MAPPATO'


def select_configuration(row, configs):
    # Restituisce: Partner, Esito, Decorrenza, Gettone RES/IVA, Ricorrente RES/IVA, Partner storico.
    # Partner = agente con modello attivo alla sottoscrizione (usato per le commissioni).
    # Partner storico = agente a prescindere dalla decorrenza del modello (usato per il Cohort Churn).
    candidates, outcome = configuration_candidates(row, configs)
    signed_month = row['Mese sottoscrizione']
    if candidates.empty:
        return pd.Series([None, outcome, pd.NaT, None, None, None, None, None])

    sub = row.get('Subchannel')
    effective, reasons = [], []
    for agent, grp in candidates.groupby('Agente', sort=False):
        dated = grp[grp['Decorrenza'].notna()].sort_values('Decorrenza')
        if pd.notna(signed_month):
            in_force = dated[dated['Decorrenza'] <= signed_month]
        else:
            in_force = dated.iloc[0:0]
        if not in_force.empty:
            cfg, attivo = in_force.iloc[-1], True
        elif not dated.empty:
            cfg, attivo = dated.iloc[0], False
        else:
            cfg, attivo = grp.iloc[0], False
        # ESCLUDI SELF / ESCLUDI GD valgono per la configurazione dell'agente in vigore
        # e prevalgono anche sul match da Promo code.
        why = exclusion_reason(sub, cfg.get('ESCLUDI SELF'), cfg.get('ESCLUDI GD'))
        if why:
            reasons.append(why)
        else:
            effective.append((agent, cfg, attivo))

    if not effective:
        return pd.Series([None, reasons[0], pd.NaT, None, None, None, None, None])

    agents = {agent for agent, _, _ in effective}
    historic_partner = next(iter(agents)) if len(agents) == 1 else None
    in_force_rows = [cfg for _, cfg, attivo in effective if attivo]
    if not in_force_rows:
        # Il mapping può essere noto, ma il modello non ancora attivo.
        return pd.Series([None, outcome + '_MODELLO_NON_ATTIVO', pd.NaT, None, None, None, None, historic_partner])
    if len(in_force_rows) > 1:
        # Più agenti con modello attivo per lo stesso contratto: non si sceglie in silenzio.
        return pd.Series([None, 'CONFLITTO_PARTNER', pd.NaT, None, None, None, None, None])
    chosen = in_force_rows[0]
    return pd.Series([
        chosen['Agente'], outcome, chosen['Decorrenza'], chosen['GETTONE RES'],
        chosen['GETTONE IVA'], chosen['RICORRENTE RES'], chosen['RICORRENTE IVA'], historic_partner
    ])


# Stati che danno diritto al gettone (Base e Avanzato): tutti tranne ANNULLATO e SOSPESO.
# Nel report INSERITO equivale a IN ATTESA e viene normalizzato da clean_status().
GETTONE_STATI_VALIDI = ['ATTIVO', 'IN ATTESA', 'IN ATTIVAZIONE', 'CHIUSO']
STATI_NOTI = {'ATTIVO', 'ANNULLATO', 'CHIUSO', 'IN ATTIVAZIONE', 'IN ATTESA', 'SOSPESO'}

# Malus per chiusura. La vita della fornitura conta solo per mese di calendario, il giorno è
# ignorato: attivazione 1 luglio e chiusura 31 luglio = 1 mese; 15 gennaio -> 20 agosto = 8 mesi.
# Fino a 4 mesi di vita = malus 100%; 5 e 6 mesi = 50%; oltre il sesto mese nessun malus.
# Una chiusura senza attivazione è trattata come churn a 3 mesi (malus 100%).
MALUS_100_FINO_A_MESI = 4
MALUS_50_FINO_A_MESI = 6

# Esclusioni per agente (colonne ESCLUDI SELF / ESCLUDI GD del file identificatori).
SUBCHANNEL_SELF = {'', 'web'}
SUBCHANNEL_GD = {'nenb2c', 'nenb2b'}

# Bonus Churn: classi sul tasso di partenza, in decimi di punto percentuale (189 = 18,9%).
BONUS_CLASSI = ['PLATINUM', 'GOLD', 'SILVER', 'BRONZE', 'BEGINNER']
BONUS_LIMITI_CLASSI = [189, 229, 269, 300]
# Micro-classi BEGINNER: (limite massimo, etichetta, miglioramento trimestrale, miglioramento annuo),
# in decimi di punto percentuale.
BONUS_MICRO_CLASSI = [
    (339, '30,1%-33,9%', 7, 21),
    (379, '34,0%-37,9%', 8, 24),
    (419, '38,0%-41,9%', 10, 30),
    (459, '42,0%-45,9%', 12, 36),
    (499, '46,0%-49,9%', 17, 51),
    (10 ** 6, '>=50,0%', 25, 75),
]


def clean_status(series):
    return series.astype(str).str.strip().str.upper().replace({'INSERITO': 'IN ATTESA'})


def is_yes(v):
    return str(v).strip().upper() in {'SI', 'SÌ', 'S', 'YES', 'TRUE', '1', '1.0'}


def exclusion_reason(subchannel, esclude_self, esclude_gd):
    n = norm(subchannel)
    if is_yes(esclude_self) and n in SUBCHANNEL_SELF:
        return 'ESCLUSO_SELF'
    if is_yes(esclude_gd) and n in SUBCHANNEL_GD:
        return 'ESCLUSO_GD'
    return None


def months_lived(start, end):
    # Mesi di vita contando solo il mese di calendario (estremi inclusi): luglio -> luglio = 1.
    # Chiusura nel mese dell'attivazione = 1; chiusura in un mese precedente = 0 o negativo.
    if pd.isna(start) or pd.isna(end):
        return pd.NA
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    return (end.year - start.year) * 12 + end.month - start.month + 1


def malus_fascia(months):
    # Mesi mancanti (chiusura senza attivazione) = churn a 3 mesi = malus 100%.
    if pd.isna(months) or months <= MALUS_100_FINO_A_MESI:
        return '100%', 1.0
    if months <= MALUS_50_FINO_A_MESI:
        return '50%', 0.5
    return '0%', 0.0


def churn_tenths(switch_out, activated):
    # Cohort Churn in decimi di punto percentuale, TRONCATO (non arrotondato), con aritmetica
    # intera per evitare errori di virgola mobile: 189 = 18,9%.
    if pd.isna(activated) or int(activated) <= 0:
        return None
    return int(switch_out) * 1000 // int(activated)


def churn_class(t):
    for name, limit in zip(BONUS_CLASSI, BONUS_LIMITI_CLASSI):
        if t <= limit:
            return name
    return 'BEGINNER'


def micro_class(t):
    for limit, label, d_q, d_a in BONUS_MICRO_CLASSI:
        if t <= limit:
            return label, d_q, d_a
    return BONUS_MICRO_CLASSI[-1][1:]


def consecutive_run(months):
    # Numero di mesi consecutivi che terminano con l'ultima rilevazione.
    months = sorted({pd.Timestamp(m) for m in months if pd.notna(m)})
    if not months:
        return 0
    run = 1
    for i in range(len(months) - 1, 0, -1):
        if months[i - 1] == months[i] - pd.DateOffset(months=1):
            run += 1
        else:
            break
    return run


def pooled_obs(hist, months):
    sel = hist[hist['Mese rilevazione'].isin(months)]
    return int(sel['Switch OUT'].sum()), int(sel['POD/PDR attivati'].sum()), len(sel)


def agreement_year(start, month):
    # Anno di accordo (1, 2, ...) a cui appartiene un mese: anni di 12 mesi dalla DECORRENZA BONUS CHURN
    # (l'anno 2 inizia dal tredicesimo mese).
    return ((month.year - start.year) * 12 + month.month - start.month) // 12 + 1


def snapshot_six(hist, end_month):
    # "Fotografia": media ponderata delle 6 rilevazioni mensili di Cohort Churn a 12 mesi più recenti,
    # quelle che terminano a end_month. Senza 6 rilevazioni consecutive piene non si calcola né si stima nulla.
    months = [end_month + pd.DateOffset(months=-k) for k in range(5, -1, -1)]
    so, act, n = pooled_obs(hist, months)
    return (so, act) if n == 6 and act > 0 else None


def year_quarter_ends(start, k):
    # Mesi di fine trimestre dell'anno di accordo k, a cui si scatta la fotografia. Nel primo anno la
    # misurazione parte dalla decorrenza: la prima fotografia possibile richiede 6 rilevazioni (fine 6° mese).
    y_start = start + pd.DateOffset(months=12 * (k - 1))
    ends = [y_start + pd.DateOffset(months=3 * j + 2) for j in range(4)]
    if k == 1:
        ends = [e for e in ends if e >= start + pd.DateOffset(months=5)]
    return ends


def evaluate_partner_bonus(partner, hist, start, competence):
    # Etichetta baseline, bonus trimestrali e bonus annuale dell'anno di accordo della competenza.
    # Non calcola importi: cambiano da agente ad agente e si assegnano a parte.
    # Ritorna (baseline, trimestri, annuale, info); baseline è None se non calcolabile (nessuna stima).
    hist = hist[hist['Mese rilevazione'] <= competence]
    k = agreement_year(start, competence)
    y_start = start + pd.DateOffset(months=12 * (k - 1))
    y_end = y_start + pd.DateOffset(months=11)
    info = {'Anno di accordo': k, 'Periodo anno': f'{y_start:%m/%Y}-{y_end:%m/%Y}'}

    # Baseline. Anno 1: fotografia delle prime 6 rilevazioni dalla decorrenza. Anno 2 e successivi:
    # churn annuale dell'anno precedente = media ponderata (sul numero di contratti di ciascun trimestre)
    # delle fotografie trimestrali di quell'anno.
    if k == 1:
        baseline_end = start + pd.DateOffset(months=5)
        snap = snapshot_six(hist, baseline_end) if baseline_end <= competence else None
        window = [baseline_end + pd.DateOffset(months=-j) for j in range(5, -1, -1)]
        present = int(hist['Mese rilevazione'].isin(window).sum())
        needed = 6
        origin = 'Prime 6 rilevazioni dalla decorrenza'
        message = (
            f'{partner}: baseline anno 1 non calcolabile. Servono 6 rilevazioni mensili consecutive di Cohort '
            f'Churn a 12 mesi da {window[0]:%m/%Y} a {window[-1]:%m/%Y}: presenti {present}/6. '
            'Attendere le rilevazioni minime: nessun risultato calcolato o stimato.'
        )
    else:
        prev_snaps = [
            snapshot_six(hist, e) if e <= competence else None for e in year_quarter_ends(start, k - 1)
        ]
        present = sum(1 for s in prev_snaps if s is not None)
        needed = len(prev_snaps)
        snap = (
            (sum(s[0] for s in prev_snaps), sum(s[1] for s in prev_snaps))
            if present == needed else None
        )
        origin = f'Churn annuale anno {k - 1}'
        baseline_end = y_start + pd.DateOffset(months=-1)
        message = (
            f'{partner}: baseline anno {k} non calcolabile. Coincide con il churn annuale dell\'anno {k - 1}: '
            f'servono tutte le {needed} fotografie trimestrali dell\'anno (ciascuna con 6 rilevazioni consecutive piene): '
            f'disponibili {present}/{needed}. Attendere le rilevazioni minime: nessun risultato calcolato o stimato.'
        )
    info.update({'Presenti': present, 'Attese': needed, 'Messaggio': message})
    if snap is None:
        return None, [], None, info

    so_b, act_b = snap
    t_base = churn_tenths(so_b, act_b)
    base_class = churn_class(t_base)
    if base_class == 'BEGINNER':
        micro_label, d_q, d_a = micro_class(t_base)
    else:
        micro_label, d_q, d_a = None, None, None
    baseline = {
        'Partner': partner,
        'Anno di accordo': k,
        'Periodo anno': info['Periodo anno'],
        'Origine baseline': origin,
        'Switch OUT baseline': so_b,
        'POD/PDR attivati baseline': act_b,
        'Tasso di partenza (%)': t_base / 10,
        'Classe di partenza': base_class,
        'Micro-classe BEGINNER': micro_label,
        'Miglioramento atteso trimestre (pp)': None if d_q is None else d_q / 10,
        'Miglioramento atteso anno (pp)': None if d_a is None else d_a / 10,
    }

    # Trimestri dell'anno di accordo che iniziano dopo la baseline. Il tasso trimestrale è la fotografia
    # delle 6 rilevazioni più recenti a fine trimestre.
    quarters = []
    missed = 0
    for j in range(4):
        q_start = y_start + pd.DateOffset(months=3 * j)
        q_end = q_start + pd.DateOffset(months=2)
        if q_start <= baseline_end or q_start > competence:
            continue
        snap_q = snapshot_six(hist, q_end) if q_end <= competence else None
        t_q = churn_tenths(*snap_q) if snap_q else None
        # Prime 4 classi: soglia = tasso di partenza. BEGINNER: tasso di partenza meno il miglioramento
        # atteso, cumulato con quello dei trimestri precedenti non raggiunti (solo per BEGINNER).
        target = t_base - d_q * (1 + missed) if base_class == 'BEGINNER' else t_base
        if q_end > competence:
            esito = 'IN CORSO'
        elif t_q is None:
            esito = 'RILEVAZIONI MANCANTI'
        elif t_q <= target:
            esito = 'BONUS TRIMESTRALE'
            missed = 0
        else:
            esito = 'NESSUN BONUS'
            if base_class == 'BEGINNER':
                missed += 1
        quarters.append({
            'Partner': partner,
            'Anno di accordo': k,
            'Trimestre': f'T{j + 1}',
            'Mese fotografia': q_end,
            'Switch OUT': None if snap_q is None else snap_q[0],
            'POD/PDR attivati': None if snap_q is None else snap_q[1],
            'Tasso trimestrale (%)': None if t_q is None else t_q / 10,
            'Soglia da rispettare (%)': target / 10,
            'Classe di partenza': base_class,
            'Classe tasso trimestrale': None if t_q is None else churn_class(t_q),
            'Esito': esito,
            'Da consuntivare in questa competenza': (
                'SI' if q_end == competence and esito in ('BONUS TRIMESTRALE', 'NESSUN BONUS') else 'NO'
            ),
        })

    # Annuale: media ponderata (somma Switch OUT / somma attivati, cioè sul numero di contratti di
    # ciascun trimestre) delle fotografie trimestrali dell'anno di accordo.
    annual = None
    ends = year_quarter_ends(start, k)
    snaps = [snapshot_six(hist, e) for e in ends if e <= competence]
    snaps = [s for s in snaps if s is not None]
    if snaps:
        so_a = sum(s[0] for s in snaps)
        act_a = sum(s[1] for s in snaps)
        t_a = churn_tenths(so_a, act_a)
        cls_a = churn_class(t_a)
        target_a = None if d_a is None else t_base - d_a
        if competence < y_end:
            esito_a = 'IN CORSO (PROVVISORIO)'
        elif len(snaps) < len(ends):
            esito_a = 'RILEVAZIONI MANCANTI'
        elif base_class != 'BEGINNER':
            gap = BONUS_CLASSI.index(cls_a) - BONUS_CLASSI.index(base_class)
            if cls_a == 'BEGINNER':
                # Passaggio a BEGINNER da una delle prime 4 classi: nessun premio annuale.
                esito_a = 'NESSUN BONUS'
            elif gap <= 0:
                # Stessa classe o migliore: bonus di appartenenza della classe raggiunta.
                esito_a = 'BONUS APPARTENENZA ' + cls_a
            else:
                # Peggioramento (anche di più classi) ma ancora tra le prime 4: classe di atterraggio.
                esito_a = 'BONUS APPARTENENZA ' + cls_a + ' (classe di atterraggio)'
        elif cls_a != 'BEGINNER':
            esito_a = 'BONUS APPARTENENZA ' + cls_a
        elif t_a <= target_a:
            esito_a = 'BONUS MIGLIORAMENTO ANNUALE BEGINNER ' + micro_label
        else:
            esito_a = 'NESSUN BONUS'
        annual = {
            'Partner': partner,
            'Anno di accordo': k,
            'Periodo anno': info['Periodo anno'],
            'Fotografie trimestrali disponibili': len(snaps),
            'Fotografie trimestrali attese': len(ends),
            'Switch OUT': so_a,
            'POD/PDR attivati': act_a,
            'Tasso annuale (%)': t_a / 10,
            'Target annuale BEGINNER (%)': None if target_a is None else target_a / 10,
            'Classe di partenza': base_class,
            'Classe tasso annuale': cls_a,
            'Esito': esito_a,
            'Da consuntivare in questa competenza': (
                'SI' if competence == y_end and len(snaps) == len(ends) else 'NO'
            ),
        }
    return baseline, quarters, annual, info


def join_reasons(flags):
    return pd.Series(
        ['; '.join(flags.columns[row]) for row in flags.to_numpy()],
        index=flags.index, dtype='object'
    )


def read_excel(upload, sheet_name=0):
    return pd.read_excel(upload, sheet_name=sheet_name, engine='openpyxl')


def to_excel(sheets):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.book[name[:31]]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                vals = [str(c.value) if c.value is not None else '' for c in col[:2000]]
                width = min(max(max((len(v) for v in vals), default=8) + 2, 10), 45)
                ws.column_dimensions[col[0].column_letter].width = width
    out.seek(0)
    return out.getvalue()


MONTH_OPTIONS = pd.period_range('2025-01', '2032-12', freq='M').astype(str).tolist()
with st.sidebar:
    module = st.radio(
        'Funzione',
        ['Commissioni Base', 'Commissioni Avanzato', 'Bonus Churn - rilevazioni e idoneità']
    )
    competence_label = st.selectbox(
        'Mese di competenza / rilevazione',
        MONTH_OPTIONS,
        index=MONTH_OPTIONS.index(DEFAULT_COMPETENCE.strftime('%Y-%m')),
    )
    competence = pd.Timestamp(f'{competence_label}-01')
    st.info('Decorrenze, importi e adesione al Bonus Churn sono letti dal file identificatori.')

contracts_file = st.file_uploader('1. Carica report contratti', type='xlsx')
mapping_file = st.file_uploader('2. Carica file identificatori e condizioni', type='xlsx')
cohort_ledger_file = st.file_uploader('3. Registro storico Cohort Churn (opzionale)', type='xlsx', help='Usato solo dal modulo Bonus Churn. Al primo calcolo può essere lasciato vuoto.')

if contracts_file and mapping_file:
    contracts = read_excel(contracts_file)
    mapping_sheet = 'Base' if module == 'Commissioni Base' else 'Avanzato'
    try:
        mapping = read_excel(mapping_file, sheet_name=mapping_sheet)
    except ValueError:
        st.error(f'Il file identificatori non contiene il foglio richiesto: {mapping_sheet}.')
        st.stop()

    required = {
        'Contract quote date', 'Status from PoD', 'Subscription Name',
        'Customer type', 'Subchannel', 'Promo code',
        'Prospected activation date', 'Point of delivery: Closing date',
        'Point of delivery: Point of delivery Name'
    }
    missing = required - set(contracts.columns)
    if missing:
        st.error('Colonne mancanti nel report: ' + ', '.join(sorted(missing)))
        st.stop()
    if contracts.empty:
        st.error('Il report contratti è vuoto.')
        st.stop()

    if module == 'Commissioni Base':
        st.header('Commissioni Base')
        base_required = {
            'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
            'ESCLUDI SELF', 'ESCLUDI GD',
            'GETTONE RES', 'GETTONE IVA', 'PREMIO UTENTI ATTIVI',
            'MESI CALCOLO PREMIO DA ATTIVAZIONE', 'STORNO UTENTI CESSATI',
            'MESI CALCOLO STORNO DA ATTIVAZIONE'
        }
        base_missing = base_required - set(mapping.columns)
        if base_missing:
            st.error('Colonne mancanti nel foglio Base: ' + ', '.join(sorted(base_missing)))
            st.stop()

        base_configs = mapping.copy()
        base_configs['Sub IDs'] = base_configs['IDENTIFICATORI SUBCHANNEL'].apply(split_ids)
        base_configs['Promo IDs'] = base_configs['IDENTIFICATORI PROMO CODE'].apply(split_ids)
        numeric_cols = [
            'GETTONE RES', 'GETTONE IVA', 'PREMIO UTENTI ATTIVI',
            'MESI CALCOLO PREMIO DA ATTIVAZIONE', 'STORNO UTENTI CESSATI',
            'MESI CALCOLO STORNO DA ATTIVAZIONE'
        ]
        for c in numeric_cols:
            base_configs[c] = pd.to_numeric(base_configs[c], errors='coerce')

        base_df = contracts.copy()
        base_df['Data sottoscrizione'] = parse_dates(base_df['Contract quote date'])
        base_df['Data attivazione'] = parse_dates(base_df['Prospected activation date'])
        base_df['Data chiusura'] = parse_dates(base_df['Point of delivery: Closing date'])
        base_df['Mese sottoscrizione'] = base_df['Data sottoscrizione'].map(month)
        base_df['Mese attivazione'] = base_df['Data attivazione'].map(month)
        base_df['Mese chiusura'] = base_df['Data chiusura'].map(month)
        base_df['Stato'] = clean_status(base_df['Status from PoD'])
        base_df['Subscription Name'] = base_df['Subscription Name'].astype(str).str.strip()
        base_df['Point of Delivery'] = base_df['Point of delivery: Point of delivery Name'].astype(str).str.strip()

        def select_base(row):
            empty = [pd.NA] * 6
            sub_hits = base_configs[base_configs['Sub IDs'].apply(
                lambda ids: matches_subchannel(row.get('Subchannel'), ids)
            )]
            promo_hits = base_configs[base_configs['Promo IDs'].apply(
                lambda ids: contains_promo(row.get('Promo code'), ids)
            )]
            # Sub IDs e Promo IDs contengono liste, quindi non sono hashable.
            # Uniamo gli indici delle configurazioni trovate, evitando duplicati
            # senza applicare drop_duplicates() all'intero DataFrame.
            hit_indexes = sub_hits.index.union(promo_hits.index)
            hits = base_configs.loc[hit_indexes].copy()
            if hits.empty:
                return pd.Series([pd.NA, 'NON_MAPPATO'] + empty)
            # ESCLUDI SELF / ESCLUDI GD prevalgono anche sul match da Promo code.
            reasons = hits.apply(
                lambda r: exclusion_reason(row.get('Subchannel'), r['ESCLUDI SELF'], r['ESCLUDI GD']), axis=1
            )
            hits = hits[reasons.isna()]
            if hits.empty:
                return pd.Series([pd.NA, reasons.dropna().iloc[0]] + empty)
            agents = hits['Agente'].dropna().astype(str).unique().tolist()
            if len(agents) == 0:
                return pd.Series([pd.NA, 'NON_MAPPATO'] + empty)
            if len(agents) > 1:
                return pd.Series([pd.NA, 'CONFLITTO_SUBCHANNEL_PROMO'] + empty)
            cfg = hits[hits['Agente'].astype(str) == agents[0]].iloc[0]
            return pd.Series([
                agents[0], 'MAPPATO', cfg['GETTONE RES'], cfg['GETTONE IVA'],
                cfg['PREMIO UTENTI ATTIVI'], cfg['MESI CALCOLO PREMIO DA ATTIVAZIONE'],
                cfg['STORNO UTENTI CESSATI'], cfg['MESI CALCOLO STORNO DA ATTIVAZIONE']
            ])

        # Il mapping dipende solo da (Subchannel, Promo code): una volta per combinazione.
        base_keys = ['Subchannel', 'Promo code']
        base_combos = base_df[base_keys].drop_duplicates().reset_index(drop=True)
        selected_base = base_combos.apply(select_base, axis=1)
        selected_base.columns = [
            'Partner', 'Esito mapping', 'Gettone RES', 'Gettone IVA',
            'Premio utenti attivi', 'Mesi premio', 'Storno utenti cessati', 'Mesi storno'
        ]
        base_combos = pd.concat([base_combos, selected_base], axis=1)
        base_df = base_df.merge(base_combos, on=base_keys, how='left')
        base_df['Segmento'] = base_df['Customer type'].map({'Person': 'Residenziale', 'Partita IVA': 'Business'})
        base_df['Gettone base'] = base_df.apply(
            lambda r: r['Gettone RES'] if r['Customer type'] == 'Person' else (
                r['Gettone IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
            ), axis=1
        )

        # Gettone base: contratti generati nel mese di competenza con stato valido
        # (tutti tranne ANNULLATO e SOSPESO, CHIUSO incluso). Vale per tutti gli agenti Base.
        base_gettoni = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & base_df['Stato'].isin(GETTONE_STATI_VALIDI)
            & base_df['Gettone base'].notna()
        ].copy()
        base_gettoni['Tipo movimento'] = 'GETTONE_BASE'
        base_gettoni['Importo'] = base_gettoni['Gettone base']

        # Annullati e sospesi del mese: segnalati per trasparenza, importo zero.
        base_esclusi_stato = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & base_df['Stato'].isin(['ANNULLATO', 'SOSPESO'])
        ].copy()
        base_esclusi_stato['Tipo movimento'] = 'ESCLUSO_PER_STATO'
        base_esclusi_stato['Importo'] = 0.0

        # Premio: coorte attivata X mesi prima e ancora ATTIVA nella competenza.
        base_premi = base_df[
            base_df['Partner'].notna()
            & base_df['Premio utenti attivi'].notna()
            & base_df['Mesi premio'].notna()
            & (base_df['Stato'] == 'ATTIVO')
        ].copy()
        base_premi['Mese obiettivo premio'] = base_premi['Mesi premio'].apply(
            lambda x: competence - pd.DateOffset(months=int(x))
        )
        base_premi = base_premi[
            base_premi['Mese attivazione'] == base_premi['Mese obiettivo premio']
        ].copy()
        base_premi['Tipo movimento'] = 'PREMIO_UTENTI_ATTIVI'
        base_premi['Importo'] = base_premi['Premio utenti attivi']

        # Storno: coorte sottoscritta X + 2 mesi prima e oggi CHIUSA.
        base_storni = base_df[
            base_df['Partner'].notna()
            & base_df['Storno utenti cessati'].notna()
            & base_df['Mesi storno'].notna()
            & (base_df['Stato'] == 'CHIUSO')
        ].copy()
        base_storni['Mesi tecnici pre-attivazione'] = 2
        base_storni['Mese obiettivo storno'] = base_storni['Mesi storno'].apply(
            lambda x: competence - pd.DateOffset(months=int(x) + 2)
        )
        base_storni = base_storni[
            base_storni['Mese sottoscrizione'] == base_storni['Mese obiettivo storno']
        ].copy()
        base_storni['Tipo movimento'] = 'STORNO_UTENTI_CESSATI'
        base_storni['Importo'] = -base_storni['Storno utenti cessati'].abs()

        base_movements = pd.concat([base_gettoni, base_premi, base_storni], ignore_index=True)
        base_summary = base_movements.pivot_table(
            index='Partner', columns='Tipo movimento', values='Importo', aggfunc='sum', fill_value=0
        ).reset_index()
        for c in ['GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI']:
            if c not in base_summary:
                base_summary[c] = 0.0
        base_summary['TOTALE_NETTO'] = base_summary[
            ['GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI']
        ].sum(axis=1)
        base_summary = base_summary[
            ['Partner', 'GETTONE_BASE', 'PREMIO_UTENTI_ATTIVI', 'STORNO_UTENTI_CESSATI', 'TOTALE_NETTO']
        ].sort_values('Partner')

        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Gettone base', f"€ {base_gettoni['Importo'].sum():,.2f}")
        c2.metric('Premialità', f"€ {base_premi['Importo'].sum():,.2f}")
        c3.metric('Storni', f"€ {base_storni['Importo'].sum():,.2f}")
        c4.metric('Totale netto', f"€ {base_movements['Importo'].sum():,.2f}")

        st.subheader('Sintesi agenti e report individuali')
        base_partners = sorted(
            set(base_gettoni['Partner'].dropna())
            | set(base_premi['Partner'].dropna())
            | set(base_storni['Partner'].dropna())
        )
        for partner in base_partners:
            p_gettoni = base_gettoni[base_gettoni['Partner'] == partner].copy()
            p_premi = base_premi[base_premi['Partner'] == partner].copy()
            p_storni = base_storni[base_storni['Partner'] == partner].copy()
            amount_base = float(p_gettoni['Importo'].sum())
            amount_premio = float(p_premi['Importo'].sum())
            amount_storno = float(p_storni['Importo'].sum())
            amount_netto = amount_base + amount_premio + amount_storno
            p_summary = pd.DataFrame([
                {'Voce': 'Contratti generati nel mese', 'Numero': len(p_gettoni), 'Importo': amount_base},
                {'Voce': 'Utenti attivi premiati', 'Numero': len(p_premi), 'Importo': amount_premio},
                {'Voce': 'Utenti cessati stornati', 'Numero': len(p_storni), 'Importo': amount_storno},
                {'Voce': 'TOTALE NETTO', 'Numero': pd.NA, 'Importo': amount_netto},
            ])
            partner_export = to_excel({
                'Sintesi': p_summary,
                'Contratti del mese': p_gettoni,
                'Premio utenti attivi': p_premi,
                'Storno utenti cessati': p_storni,
            })
            safe_partner = re.sub(r'[^A-Za-z0-9._-]+', '_', str(partner)).strip('_') or 'partner'
            row = st.columns([2.2, 1.2, 1.2, 1.2, 1.2, 1.2])
            row[0].write(f'**{partner}**')
            row[1].write(f'Base: € {amount_base:,.2f}')
            row[2].write(f'Premio: € {amount_premio:,.2f}')
            row[3].write(f'Storno: € {amount_storno:,.2f}')
            row[4].write(f'Netto: € {amount_netto:,.2f}')
            row[5].download_button(
                'Scarica report', partner_export,
                file_name=f'report_base_{safe_partner}_{competence:%Y_%m}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key=f'base_{safe_partner}_{competence:%Y_%m}'
            )

        # Controlli limitati ai contratti della competenza (non all'intero report).
        base_rilevante = base_df['Mese sottoscrizione'] == competence
        base_unmapped = base_df[
            base_rilevante & base_df['Esito mapping'].isin(['NON_MAPPATO', 'CONFLITTO_SUBCHANNEL_PROMO'])
        ].copy()
        base_excl_sg = base_df[
            base_rilevante & base_df['Esito mapping'].isin(['ESCLUSO_SELF', 'ESCLUSO_GD'])
        ].copy()
        base_incomplete = base_df[
            base_df['Partner'].notna()
            & base_rilevante
            & base_df['Gettone base'].isna()
        ].copy()
        st.subheader('Controlli')
        st.write(
            f'Non mappati/conflitti: **{len(base_unmapped)}** | '
            f'Esclusi SELF/GD: **{len(base_excl_sg)}** | '
            f'Annullati/sospesi del mese: **{len(base_esclusi_stato)}** | '
            f'Gettoni mancanti per segmento: **{len(base_incomplete)}**'
        )
        base_export = to_excel({
            'Sintesi agenti': base_summary,
            'Movimenti': base_movements,
            'Contratti del mese': base_gettoni,
            'Premio utenti attivi': base_premi,
            'Storno utenti cessati': base_storni,
            'Annullati e sospesi': base_esclusi_stato,
            'Non mappati': base_unmapped,
            'Esclusi SELF-GD': base_excl_sg,
            'Config incomplete': base_incomplete,
        })
        st.download_button(
            'Scarica risultato completo Base', base_export,
            file_name=f'commissioni_base_{competence:%Y_%m}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        st.stop()

    map_required = {
        'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
        'DECORRENZA', 'ESCLUDI SELF', 'ESCLUDI GD',
        'GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA'
    }
    map_missing = map_required - set(mapping.columns)
    if map_missing:
        st.error('Colonne mancanti nel file identificatori: ' + ', '.join(sorted(map_missing)))
        st.stop()

    configs = mapping.copy()
    configs['Decorrenza'] = configs['DECORRENZA'].apply(parse_decorrenza)
    configs['Sub IDs'] = configs['IDENTIFICATORI SUBCHANNEL'].apply(split_ids)
    configs['Promo IDs'] = configs['IDENTIFICATORI PROMO CODE'].apply(split_ids)
    # Consente versioni come SWITCHO e SWITCHO 2028 senza dipendere dal nome.
    configs['Gruppo mapping'] = configs.apply(
        lambda r: '|'.join(sorted(norm(x) for x in r['Sub IDs'])) + '//' + '|'.join(sorted(norm(x) for x in r['Promo IDs'])), axis=1
    )
    for c in ['GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA']:
        configs[c] = pd.to_numeric(configs[c], errors='coerce')

    # Campi opzionali per il programma Bonus Churn.
    if 'BONUS CHURN' not in configs.columns:
        configs['BONUS CHURN'] = 'NO'
    if 'DECORRENZA BONUS CHURN' not in configs.columns:
        configs['DECORRENZA BONUS CHURN'] = pd.NaT
    configs['Bonus churn attivo'] = configs['BONUS CHURN'].apply(
        lambda v: str(v).strip().upper() in {'SI', 'SÌ', 'YES', 'TRUE', '1'}
    )
    configs['Decorrenza bonus churn'] = configs['DECORRENZA BONUS CHURN'].apply(parse_decorrenza)

    invalid_configs = configs[
        configs['Decorrenza'].notna()
        & configs[['GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA']].isna().any(axis=1)
    ].copy()

    df = contracts.copy()
    df['Data sottoscrizione'] = parse_dates(df['Contract quote date'])
    df['Data attivazione'] = parse_dates(df['Prospected activation date'])
    df['Data chiusura'] = parse_dates(df['Point of delivery: Closing date'])
    df['Mese sottoscrizione'] = df['Data sottoscrizione'].map(month)
    df['Mese attivazione'] = df['Data attivazione'].map(month)
    df['Mese chiusura'] = df['Data chiusura'].map(month)
    df['Stato'] = clean_status(df['Status from PoD'])
    df['Subscription Name'] = df['Subscription Name'].astype(str).str.strip()
    df['Point of Delivery'] = df['Point of delivery: Point of delivery Name'].astype(str).str.strip()
    df['ID fornitura'] = df.apply(
        lambda r: f"{r['Point of Delivery']}|{r['Data attivazione']:%Y-%m-%d}"
        if r['Point of Delivery'] and pd.notna(r['Data attivazione']) else '',
        axis=1
    )
    df['ID contratto'] = df['ID fornitura']

    # Il mapping dipende solo da (Subchannel, Promo code, mese di sottoscrizione):
    # si calcola una volta per combinazione e si riporta su tutte le righe.
    sel_keys = ['Subchannel', 'Promo code', 'Mese sottoscrizione']
    sel_combos = df[sel_keys].drop_duplicates().reset_index(drop=True)
    selected = sel_combos.apply(lambda r: select_configuration(r, configs), axis=1)
    selected.columns = [
        'Partner', 'Esito mapping', 'Decorrenza partner', 'Gettone RES',
        'Gettone IVA', 'Ricorrente RES', 'Ricorrente IVA', 'Partner storico'
    ]
    sel_combos = pd.concat([sel_combos, selected], axis=1)
    df = df.merge(sel_combos, on=sel_keys, how='left')

    df['Segmento'] = df['Customer type'].map({'Person': 'Residenziale', 'Partita IVA': 'Business'})
    df['Gettone'] = df.apply(
        lambda r: r['Gettone RES'] if r['Customer type'] == 'Person' else (
            r['Gettone IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
        ), axis=1
    )
    df['Ricorrente'] = df.apply(
        lambda r: r['Ricorrente RES'] if r['Customer type'] == 'Person' else (
            r['Ricorrente IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
        ), axis=1
    )

    # Il partner/configurazione selezionato incorpora gia la decorrenza corretta per la coorte.
    eligible_scope = df['Partner'].notna() & df['Gettone'].notna() & df['Ricorrente'].notna()

    if module == 'Bonus Churn - rilevazioni e idoneità':
        st.header('Bonus Churn - rilevazioni consolidate e idoneità')
        cohort_month = competence - pd.DateOffset(months=13)
        window_start = cohort_month + pd.DateOffset(months=1)
        window_end = cohort_month + pd.DateOffset(months=12)
        st.info(
            f'Rilevazione {competence:%Y-%m}: coorte attivata in {cohort_month:%Y-%m}; '
            f'Switch OUT conteggiati da {window_start:%Y-%m} a {window_end:%Y-%m} inclusi.'
        )

        # Denominatore: forniture effettivamente attivate nella coorte.
        # Il partner della coorte è quello storico del mapping, indipendente dalla decorrenza del
        # modello commissionale: la baseline si misura anche sulle coorti precedenti all'adesione.
        # ANNULLATO è escluso; qualsiasi Closing Date nella finestra è considerata Switch OUT.
        activated = df[
            df['Partner storico'].notna()
            & (df['Mese attivazione'] == cohort_month)
            & (df['Stato'] != 'ANNULLATO')
            & df['ID fornitura'].ne('')
        ].copy()
        activated['Partner coorte'] = activated['Partner storico']
        activated['È Switch OUT'] = activated['Mese chiusura'].between(
            window_start, window_end, inclusive='both'
        )

        observations = activated.groupby('Partner coorte', as_index=False).agg(
            **{'POD/PDR attivati': ('ID contratto', 'nunique'), 'Switch OUT': ('È Switch OUT', 'sum')}
        ).rename(columns={'Partner coorte': 'Partner'})
        observations['Mese rilevazione'] = competence
        observations['Mese coorte'] = cohort_month
        observations['Cohort Churn'] = (
            observations['Switch OUT']
            / observations['POD/PDR attivati'].where(observations['POD/PDR attivati'] > 0)
        )
        observations = observations[
            ['Partner', 'Mese rilevazione', 'Mese coorte', 'POD/PDR attivati', 'Switch OUT', 'Cohort Churn']
        ]

        cohort_cols = ['Partner', 'Mese rilevazione', 'Mese coorte', 'POD/PDR attivati', 'Switch OUT', 'Cohort Churn']
        if cohort_ledger_file:
            cohort_ledger = read_excel(cohort_ledger_file)
            missing_cohort_cols = set(cohort_cols) - set(cohort_ledger.columns)
            if missing_cohort_cols:
                st.error('Il registro Cohort Churn non contiene le colonne richieste: ' + ', '.join(sorted(missing_cohort_cols)))
                st.stop()
            cohort_ledger = cohort_ledger[cohort_cols].copy()
            cohort_ledger['Mese rilevazione'] = parse_dates(cohort_ledger['Mese rilevazione']).map(month)
            cohort_ledger['Mese coorte'] = parse_dates(cohort_ledger['Mese coorte']).map(month)
            for c in ['POD/PDR attivati', 'Switch OUT', 'Cohort Churn']:
                cohort_ledger[c] = pd.to_numeric(cohort_ledger[c], errors='coerce')
        else:
            cohort_ledger = pd.DataFrame(columns=cohort_cols)

        duplicate_existing = cohort_ledger.duplicated(['Partner', 'Mese rilevazione'], keep=False)
        if duplicate_existing.any():
            st.error('Il registro Cohort Churn contiene rilevazioni duplicate per lo stesso partner e mese.')
            st.dataframe(cohort_ledger[duplicate_existing], use_container_width=True)
            st.stop()

        # La rilevazione corrente sostituisce l'eventuale versione dello stesso partner/mese.
        current_keys = set(zip(observations['Partner'], observations['Mese rilevazione']))
        keep_old = ~cohort_ledger.apply(
            lambda r: (r['Partner'], r['Mese rilevazione']) in current_keys, axis=1
        ) if not cohort_ledger.empty else pd.Series(dtype=bool)
        old_kept = cohort_ledger[keep_old].copy() if not cohort_ledger.empty else cohort_ledger.copy()
        cohort_updated = pd.concat([old_kept, observations], ignore_index=True)
        cohort_updated = cohort_updated.sort_values(['Partner', 'Mese rilevazione']).reset_index(drop=True)

        # Stato programma: servono 6 rilevazioni consolidate consecutive; nessuna baseline manuale.
        # I NaT (decorrenza "no") vanno prima, così l'ultima riga è la configurazione datata più recente.
        config_status = configs.sort_values('Decorrenza', na_position='first').groupby('Agente', as_index=False).tail(1)
        all_partners = (
            set(df['Partner storico'].dropna()) | set(df['Partner'].dropna())
            | set(config_status['Agente'].dropna())
        )
        status_rows = []
        for partner in sorted(all_partners):
            hist = cohort_updated[cohort_updated['Partner'] == partner].sort_values('Mese rilevazione')
            n_obs = len(hist)
            n_consec = consecutive_run(hist['Mese rilevazione'])
            last6 = hist.tail(6)
            act6 = last6['POD/PDR attivati'].sum()
            baseline_mobile = (
                churn_tenths(last6['Switch OUT'].sum(), act6) / 10
                if n_consec >= 6 and act6 > 0 else pd.NA
            )
            cfg = config_status[config_status['Agente'] == partner]
            configured = bool(cfg['Bonus churn attivo'].iloc[0]) if not cfg.empty else False
            start = cfg['Decorrenza bonus churn'].iloc[0] if not cfg.empty else pd.NaT
            eligible = n_consec >= 6
            active = configured and eligible and pd.notna(start) and start <= competence
            if active:
                state = 'ATTIVO'
            elif eligible and not configured:
                state = 'IDONEO - NON CONFIGURATO'
            elif configured and not eligible:
                state = 'IN MATURAZIONE - CONFIGURAZIONE ANTICIPATA'
            elif configured and eligible and (pd.isna(start) or start > competence):
                state = 'IDONEO - IN ATTESA DECORRENZA'
            else:
                state = 'IN MATURAZIONE' if n_consec < 6 else 'IDONEO'
            status_rows.append({
                'Partner': partner,
                'Rilevazioni consolidate': n_obs,
                'Rilevazioni consecutive': n_consec,
                'Rilevazioni mancanti': max(0, 6 - n_consec),
                'Baseline mobile ultime 6 (%)': baseline_mobile,
                'Bonus Churn configurato': 'SI' if configured else 'NO',
                'Decorrenza Bonus Churn': start,
                'Stato programma': state,
            })
        program_status = pd.DataFrame(status_rows)

        # Classe di partenza (baseline congelata), bonus trimestrali e bonus annuale.
        # Anni di accordo di 12 mesi dalla decorrenza (l'anno 2 parte dal 13° mese). Baseline anno 1 =
        # prime 6 rilevazioni; anno 2+ = churn annuale dell'anno precedente. Il tasso trimestrale è la
        # fotografia delle 6 rilevazioni più recenti a fine trimestre. Senza rilevazioni piene non si
        # calcola né si stima nulla: si segnala di attendere.
        baseline_rows, quarter_rows, annual_rows, waiting = [], [], [], []
        for _, cfg in config_status.iterrows():
            partner = cfg['Agente']
            start = cfg['Decorrenza bonus churn']
            if not cfg['Bonus churn attivo'] or pd.isna(start) or start > competence:
                continue
            hist = cohort_updated[cohort_updated['Partner'] == partner]
            baseline, quarters, annual, info = evaluate_partner_bonus(partner, hist, start, competence)
            if baseline is None:
                baseline_rows.append({
                    'Partner': partner, 'Anno di accordo': info['Anno di accordo'],
                    'Periodo anno': info['Periodo anno'],
                    'Rilevazioni/fotografie presenti': f"{info['Presenti']}/{info['Attese']}",
                    'Classe di partenza': 'ATTENDERE: baseline non calcolabile, nessuna stima effettuata',
                })
                waiting.append(info['Messaggio'])
                continue
            baseline_rows.append(baseline)
            quarter_rows.extend(quarters)
            if annual:
                annual_rows.append(annual)
        baseline_df = pd.DataFrame(baseline_rows)
        quarters_df = pd.DataFrame(quarter_rows)
        annual_df = pd.DataFrame(annual_rows)

        st.subheader('Rilevazione corrente')
        st.dataframe(observations, use_container_width=True)
        st.subheader('Stato partner')
        st.dataframe(program_status, use_container_width=True)
        for w_message in waiting:
            st.warning(w_message)
        if not baseline_df.empty:
            st.subheader('Classe di partenza')
            st.dataframe(baseline_df, use_container_width=True)
        if not quarters_df.empty:
            st.subheader('Bonus trimestrali: etichetta ed esito')
            st.dataframe(quarters_df, use_container_width=True)
        if not annual_df.empty:
            st.subheader('Bonus annuale: etichetta ed esito')
            st.dataframe(annual_df, use_container_width=True)
        st.caption(
            'Tassi con un decimale troncato (non arrotondato). Gli importi dei bonus non sono calcolati: '
            'dipendono dall\'agente e si assegnano a parte in base a classe ed esito.'
        )

        cohort_export = to_excel({'Registro storico Cohort Churn': cohort_updated})
        detail_sheets = {
            'Rilevazione corrente': observations,
            'Stato partner': program_status,
        }
        if not baseline_df.empty:
            detail_sheets['Classe di partenza'] = baseline_df
        if not quarters_df.empty:
            detail_sheets['Bonus trimestrali'] = quarters_df
        if not annual_df.empty:
            detail_sheets['Bonus annuali'] = annual_df
        detail_sheets['Dettaglio coorte'] = activated
        detail_sheets['Registro storico'] = cohort_updated
        detail_export = to_excel(detail_sheets)
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                'Scarica registro Cohort Churn aggiornato', cohort_export,
                file_name=f'registro_cohort_churn_{competence:%Y_%m}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        with d2:
            st.download_button(
                'Scarica analisi Cohort Churn completa', detail_export,
                file_name=f'analisi_cohort_churn_{competence:%Y_%m}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        st.stop()

    # Gettone Avanzato: stati validi = tutti tranne ANNULLATO e SOSPESO (CHIUSO incluso).
    in_competence = df['Mese sottoscrizione'] == competence
    initial = df[
        eligible_scope
        & in_competence
        & df['Stato'].isin(GETTONE_STATI_VALIDI)
    ].copy()
    initial['Tipo movimento'] = 'GETTONE_INIZIALE'
    initial['Importo'] = initial['Gettone']

    cancelled = df[eligible_scope & in_competence & (df['Stato'] == 'ANNULLATO')].copy()
    cancelled['Tipo movimento'] = 'ANNULLAMENTO_SEGNALATO'
    cancelled['Importo'] = 0.0

    suspended = df[eligible_scope & in_competence & (df['Stato'] == 'SOSPESO')].copy()
    suspended['Tipo movimento'] = 'SOSPESO_SEGNALATO'
    suspended['Importo'] = 0.0

    # Ricorrente dal primo mese pieno, solo per contratti ATTIVO. Il mese della chiusura è escluso
    # perché non è completo (una chiusura già pianificata non toglie il ricorrente dei mesi precedenti).
    df['Mese decorrenza mini-gettone'] = df['Data attivazione'].apply(
        lambda d: pd.NaT if pd.isna(d) else (
            d.to_period('M').to_timestamp()
            if d.day == 1
            else d.to_period('M').to_timestamp() + pd.offsets.MonthBegin(1)
        )
    )
    recurring = df[
        eligible_scope
        & (df['Stato'] == 'ATTIVO')
        & df['Mese decorrenza mini-gettone'].notna()
        & (df['Mese decorrenza mini-gettone'] <= competence)
        & (df['Mese chiusura'].isna() | (competence < df['Mese chiusura']))
    ].copy()
    recurring['Tipo movimento'] = 'RICORRENTE'
    recurring['Importo'] = recurring['Ricorrente']

    # Ogni chiusura appartiene a una sola competenza: il mese della Closing Date.
    # Il malus riguarda solo contratti che avrebbero preso il gettone (stato valido, quindi non ANNULLATO).
    # Conta solo il mese di calendario; una chiusura senza attivazione vale come churn a 3 mesi (100%).
    churn_scope = (
        eligible_scope
        & df['Stato'].isin(GETTONE_STATI_VALIDI)
        & (df['Mese chiusura'] == competence)
    )
    churn = df[churn_scope].copy()
    churn['Mesi di vita'] = [
        months_lived(a, c) for a, c in zip(churn['Data attivazione'], churn['Data chiusura'])
    ]
    fasce = [malus_fascia(m) for m in churn['Mesi di vita']]
    churn['Fascia malus'] = [f for f, _ in fasce]
    churn['Motivo malus'] = [
        'Chiusura senza attivazione (trattata come churn a 3 mesi)' if pd.isna(m)
        else ("Chiusura prima dell'attivazione" if m <= 0 else f'Chiusura al mese {int(m)} di vita')
        for m in churn['Mesi di vita']
    ]
    churn['Importo'] = [-float(g) * share for (_, share), g in zip(fasce, churn['Gettone'])]
    no_activation = churn[churn['Data attivazione'].isna()].copy()
    malus_new = churn[churn['Importo'] != 0].copy()
    malus_new['Tipo movimento'] = 'MALUS_CHURN'

    cols = [
        'ID fornitura', 'Point of Delivery', 'Subscription Name',
        'Partner', 'Segmento', 'Customer type', 'Stato',
        'Contract quote date', 'Prospected activation date', 'Point of delivery: Closing date',
        'Subchannel', 'Promo code', 'Tipo movimento', 'Importo'
    ]
    movements = pd.concat([initial[cols], recurring[cols], malus_new[cols]], ignore_index=True)

    summary = movements.pivot_table(
        index='Partner', columns='Tipo movimento', values='Importo', aggfunc='sum', fill_value=0
    ).reset_index()
    for c in ['GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN']:
        if c not in summary:
            summary[c] = 0.0
    summary['TOTALE_DA_PAGARE'] = summary[
        ['GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN']
    ].sum(axis=1)
    summary = summary[
        ['Partner', 'GETTONE_INIZIALE', 'RICORRENTE', 'MALUS_CHURN', 'TOTALE_DA_PAGARE']
    ].sort_values('Partner')

    # Controlli limitati ai contratti rilevanti per la competenza (sottoscritti o chiusi nel mese),
    # non all'intero report.
    rilevante = in_competence | (df['Mese chiusura'] == competence)
    unmapped = df[rilevante & df['Esito mapping'].isin([
        'NON_MAPPATO', 'NON_MAPPATO_BILLOO_PROMO_NON_SUFFICIENTE',
        'CONFLITTO_SUBCHANNEL_PROMO', 'CONFLITTO_PARTNER'
    ])].copy()
    excluded = df[rilevante & df['Esito mapping'].str.contains('MODELLO_NON_ATTIVO', na=False)].copy()
    excluded_sg = df[rilevante & df['Esito mapping'].isin(['ESCLUSO_SELF', 'ESCLUSO_GD'])].copy()

    duplicate_supply = df['ID fornitura'].ne('') & df.duplicated('ID fornitura', keep=False)
    anomaly_flags = pd.DataFrame({
        'Data sottoscrizione mancante': df['Data sottoscrizione'].isna(),
        'Segmento non riconosciuto': df['Segmento'].isna(),
        'POD/PDR mancante': df['Point of Delivery'].eq(''),
        'Attivazione mancante': (df['Stato'] != 'ANNULLATO') & df['Data attivazione'].isna(),
        'Chiusura senza attivazione': df['Data chiusura'].notna() & df['Data attivazione'].isna(),
        "Chiusura prima dell'attivazione": df['Data chiusura'].notna() & (df['Data chiusura'] < df['Data attivazione']),
        'ID fornitura duplicato': duplicate_supply,
        'Stato non riconosciuto': ~df['Stato'].isin(STATI_NOTI),
        'CHIUSO senza Closing date': (df['Stato'] == 'CHIUSO') & df['Data chiusura'].isna(),
    }, index=df.index)
    anomaly_scope = rilevante | (df['Partner'].notna() & (df['Stato'] == 'ATTIVO')) | df['Data sottoscrizione'].isna()
    anomalies = df[anomaly_scope & anomaly_flags.any(axis=1)].copy()
    anomalies['Motivi anomalia'] = join_reasons(anomaly_flags.loc[anomalies.index])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Gettoni iniziali', f"€ {initial['Importo'].sum():,.2f}")
    c2.metric('Ricorrenti', f"€ {recurring['Importo'].sum():,.2f}")
    c3.metric('Nuovi malus', f"€ {malus_new['Importo'].sum():,.2f}")
    c4.metric('Totale', f"€ {movements['Importo'].sum():,.2f}")

    st.subheader('Sintesi partner')
    st.dataframe(summary, use_container_width=True)
    st.subheader('Controlli')
    st.write(
        f'Non mappati/conflitti: **{len(unmapped)}** | '
        f'Esclusi SELF/GD: **{len(excluded_sg)}** | '
        f'Partner con modello non attivo: **{len(excluded)}** | '
        f'Sospesi del mese: **{len(suspended)}** | '
        f'Anomalie dati: **{len(anomalies)}** | '
        f'Chiusure senza attivazione (incluse nei malus al 100%): **{len(no_activation)}** | '
        f'Configurazioni incomplete: **{len(invalid_configs)}** | '
        f'Malus della competenza: **{len(malus_new)}**'
    )
    st.caption(
        f'Malus (conta solo il mese di calendario, non il giorno): fino a {MALUS_100_FINO_A_MESI} mesi di vita = 100%; '
        f'mesi {MALUS_100_FINO_A_MESI + 1}-{MALUS_50_FINO_A_MESI} = 50%; oltre il {MALUS_50_FINO_A_MESI}° mese nessun malus. '
        'Chiusure senza attivazione = churn a 3 mesi = 100%.'
    )

    export = to_excel({
        'Sintesi partner': summary,
        'Movimenti': movements,
        'Gettoni iniziali': initial,
        'Annullamenti': cancelled,
        'Sospesi': suspended,
        'Ricorrenti': recurring,
        'Malus del mese': malus_new,
        'Chiusure senza attivazione': no_activation,
        'Non mappati': unmapped,
        'Esclusi SELF-GD': excluded_sg,
        'Partner esclusi': excluded,
        'Anomalie': anomalies,
        'Config incomplete': invalid_configs,
        'Dati classificati': df,
    })
    st.subheader('Download operativi')
    st.caption('I malus sono determinati direttamente dalla Closing Date: non è più necessario conservare o ricaricare uno storico malus.')
    malus_month_export = to_excel({'Malus del mese': malus_new})
    d1, d2 = st.columns(2)
    with d1:
        st.download_button('Scarica malus del mese', malus_month_export, file_name=f'malus_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with d2:
        st.download_button('Scarica risultato completo', export, file_name=f'commissioni_{competence:%Y_%m}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
else:
    st.warning('Carica il report contratti e il file identificatori per eseguire il calcolo.')
