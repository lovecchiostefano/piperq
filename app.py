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
    candidates, outcome = configuration_candidates(row, configs)
    signed_month = row['Mese sottoscrizione']
    active = candidates[candidates['Decorrenza'].notna() & (candidates['Decorrenza'] <= signed_month)].copy()
    if active.empty:
        # Il mapping può essere noto, ma il modello non ancora attivo.
        if not candidates.empty:
            return pd.Series([None, outcome + '_MODELLO_NON_ATTIVO', pd.NaT, None, None, None, None])
        return pd.Series([None, outcome, pd.NaT, None, None, None, None])
    chosen = active.sort_values('Decorrenza').iloc[-1]
    return pd.Series([
        chosen['Agente'], outcome, chosen['Decorrenza'], chosen['GETTONE RES'],
        chosen['GETTONE IVA'], chosen['RICORRENTE RES'], chosen['RICORRENTE IVA']
    ])


def months_inclusive(start, end):
    if pd.isna(start) or pd.isna(end):
        return pd.NA
    return (end.year - start.year) * 12 + end.month - start.month + 1


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

    if module == 'Commissioni Base':
        st.header('Commissioni Base')
        base_required = {
            'Agente', 'IDENTIFICATORI SUBCHANNEL', 'IDENTIFICATORI PROMO CODE',
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
        base_df['Stato'] = base_df['Status from PoD'].astype(str).str.strip().str.upper()
        base_df['Subscription Name'] = base_df['Subscription Name'].astype(str).str.strip()
        base_df['Point of Delivery'] = base_df['Point of delivery: Point of delivery Name'].astype(str).str.strip()

        def select_base(row):
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
            agents = hits['Agente'].dropna().astype(str).unique().tolist()
            if len(agents) == 0:
                return pd.Series([pd.NA, 'NON_MAPPATO', pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA])
            if len(agents) > 1:
                return pd.Series([pd.NA, 'CONFLITTO_SUBCHANNEL_PROMO', pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA])
            cfg = hits[hits['Agente'].astype(str) == agents[0]].iloc[0]
            return pd.Series([
                agents[0], 'MAPPATO', cfg['GETTONE RES'], cfg['GETTONE IVA'],
                cfg['PREMIO UTENTI ATTIVI'], cfg['MESI CALCOLO PREMIO DA ATTIVAZIONE'],
                cfg['STORNO UTENTI CESSATI'], cfg['MESI CALCOLO STORNO DA ATTIVAZIONE']
            ])

        selected_base = base_df.apply(select_base, axis=1)
        selected_base.columns = [
            'Partner', 'Esito mapping', 'Gettone RES', 'Gettone IVA',
            'Premio utenti attivi', 'Mesi premio', 'Storno utenti cessati', 'Mesi storno'
        ]
        base_df = pd.concat([base_df, selected_base], axis=1)
        base_df['Segmento'] = base_df['Customer type'].map({'Person': 'Residenziale', 'Partita IVA': 'Business'})
        base_df['Gettone base'] = base_df.apply(
            lambda r: r['Gettone RES'] if r['Customer type'] == 'Person' else (
                r['Gettone IVA'] if r['Customer type'] == 'Partita IVA' else pd.NA
            ), axis=1
        )

        # Gettone base: contratti generati nel mese, esclusi gli ANNULLATO.
        # L'esclusione vale per tutti gli agenti del modello Base.
        base_gettoni = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & (base_df['Stato'] != 'ANNULLATO')
            & base_df['Gettone base'].notna()
        ].copy()
        base_gettoni['Tipo movimento'] = 'GETTONE_BASE'
        base_gettoni['Importo'] = base_gettoni['Gettone base']

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

        base_unmapped = base_df[base_df['Esito mapping'] != 'MAPPATO'].copy()
        base_incomplete = base_df[
            base_df['Partner'].notna()
            & (base_df['Mese sottoscrizione'] == competence)
            & base_df['Gettone base'].isna()
        ].copy()
        st.subheader('Controlli')
        st.write(
            f'Non mappati/conflitti: **{len(base_unmapped)}** | '
            f'Gettoni mancanti per segmento: **{len(base_incomplete)}**'
        )
        base_export = to_excel({
            'Sintesi agenti': base_summary,
            'Movimenti': base_movements,
            'Contratti del mese': base_gettoni,
            'Premio utenti attivi': base_premi,
            'Storno utenti cessati': base_storni,
            'Non mappati': base_unmapped,
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
        'DECORRENZA', 'GETTONE RES', 'GETTONE IVA', 'RICORRENTE RES', 'RICORRENTE IVA'
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
    df['Stato'] = df['Status from PoD'].astype(str).str.strip().str.upper()
    df['Subscription Name'] = df['Subscription Name'].astype(str).str.strip()
    df['Point of Delivery'] = df['Point of delivery: Point of delivery Name'].astype(str).str.strip()
    df['ID fornitura'] = df.apply(
        lambda r: f"{r['Point of Delivery']}|{r['Data attivazione']:%Y-%m-%d}"
        if r['Point of Delivery'] and pd.notna(r['Data attivazione']) else '',
        axis=1
    )
    df['ID contratto'] = df['ID fornitura']

    selected = df.apply(lambda r: select_configuration(r, configs), axis=1)
    selected.columns = [
        'Partner', 'Esito mapping', 'Decorrenza partner', 'Gettone RES',
        'Gettone IVA', 'Ricorrente RES', 'Ricorrente IVA'
    ]
    df = pd.concat([df, selected], axis=1)

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
        # ANNULLATO è escluso; la Closing Date identifica direttamente l'eventuale Switch OUT.
        activated = df[
            df['Partner'].notna()
            & (df['Mese attivazione'] == cohort_month)
            & (df['Stato'] != 'ANNULLATO')
            & df['ID fornitura'].ne('')
        ].copy()
        activated['È Switch OUT'] = activated['Mese chiusura'].between(
            window_start, window_end, inclusive='both'
        )

        observations = activated.groupby('Partner', as_index=False).agg(
            **{'POD/PDR attivati': ('ID contratto', 'nunique'), 'Switch OUT': ('È Switch OUT', 'sum')}
        )
        observations['Mese rilevazione'] = competence
        observations['Mese coorte'] = cohort_month
        observations['Cohort Churn'] = observations.apply(
            lambda r: r['Switch OUT'] / r['POD/PDR attivati'] if r['POD/PDR attivati'] else pd.NA,
            axis=1
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

        # Stato programma: servono 6 rilevazioni consolidate; nessuna baseline manuale.
        config_status = configs.sort_values('Decorrenza').groupby('Agente', as_index=False).tail(1)
        status_rows = []
        for partner in sorted(set(df['Partner'].dropna()) | set(config_status['Agente'].dropna())):
            hist = cohort_updated[cohort_updated['Partner'] == partner].sort_values('Mese rilevazione')
            last6 = hist.tail(6)
            n_obs = len(hist)
            baseline = (
                last6['Switch OUT'].sum() / last6['POD/PDR attivati'].sum()
                if len(last6) == 6 and last6['POD/PDR attivati'].sum() > 0 else pd.NA
            )
            cfg = config_status[config_status['Agente'] == partner]
            configured = bool(cfg['Bonus churn attivo'].iloc[0]) if not cfg.empty else False
            start = cfg['Decorrenza bonus churn'].iloc[0] if not cfg.empty else pd.NaT
            eligible = n_obs >= 6
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
                state = 'IN MATURAZIONE' if n_obs < 6 else 'IDONEO'
            status_rows.append({
                'Partner': partner,
                'Rilevazioni consolidate': n_obs,
                'Rilevazioni mancanti': max(0, 6 - n_obs),
                'Baseline ultime 6': baseline,
                'Bonus Churn configurato': 'SI' if configured else 'NO',
                'Decorrenza Bonus Churn': start,
                'Stato programma': state,
            })
        program_status = pd.DataFrame(status_rows)

        st.subheader('Rilevazione corrente')
        st.dataframe(observations, use_container_width=True)
        st.subheader('Stato partner')
        st.dataframe(program_status, use_container_width=True)

        cohort_export = to_excel({'Registro storico Cohort Churn': cohort_updated})
        detail_export = to_excel({
            'Rilevazione corrente': observations,
            'Stato partner': program_status,
            'Dettaglio coorte': activated,
            'Registro storico': cohort_updated,
        })
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

    # Gettone Avanzato: gli ANNULLATO sono sempre esclusi dal calcolo.
    initial = df[
        eligible_scope
        & (df['Mese sottoscrizione'] == competence)
        & (df['Stato'] != 'ANNULLATO')
        & df['Stato'].isin(['IN ATTIVAZIONE', 'ATTIVO', 'CHIUSO'])
    ].copy()
    initial['Tipo movimento'] = 'GETTONE_INIZIALE'
    initial['Importo'] = initial['Gettone']

    cancelled = df[
        eligible_scope
        & (df['Mese sottoscrizione'] == competence)
        & (df['Stato'] == 'ANNULLATO')
    ].copy()
    cancelled['Tipo movimento'] = 'ANNULLAMENTO_SEGNALATO'
    cancelled['Importo'] = 0.0

    # Ricorrente dal primo mese pieno. Il mese della chiusura è escluso perché non è completo.
    df['Mese decorrenza mini-gettone'] = df['Data attivazione'].apply(
        lambda d: pd.NaT if pd.isna(d) else (
            d.to_period('M').to_timestamp()
            if d.day == 1
            else d.to_period('M').to_timestamp() + pd.offsets.MonthBegin(1)
        )
    )
    recurring = df[
        eligible_scope
        & (df['Stato'] != 'ANNULLATO')
        & df['Mese decorrenza mini-gettone'].notna()
        & (df['Mese decorrenza mini-gettone'] <= competence)
        & (df['Mese chiusura'].isna() | (competence < df['Mese chiusura']))
    ].copy()
    recurring['Tipo movimento'] = 'RICORRENTE'
    recurring['Importo'] = recurring['Ricorrente']

    # Ogni chiusura appartiene a una sola competenza: il mese della Closing Date.
    churn = df[
        eligible_scope
        & (df['Mese chiusura'] == competence)
        & df['Data attivazione'].notna()
    ].copy()
    churn['Mesi attivi'] = churn.apply(
        lambda r: months_inclusive(r['Mese attivazione'], r['Mese chiusura']), axis=1
    )

    def malus(row):
        m = row['Mesi attivi']
        if pd.isna(m) or m <= 4:
            return '100%', -float(row['Gettone'])
        if m <= 6:
            return '50%', -float(row['Gettone']) * 0.5
        return '0%', 0.0

    if churn.empty:
        churn['Fascia malus'] = pd.Series(dtype='object')
        churn['Importo'] = pd.Series(dtype='float64')
    else:
        churn[['Fascia malus', 'Importo']] = churn.apply(
            lambda r: pd.Series(malus(r)), axis=1
        )
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

    unmapped = df[df['Esito mapping'].isin([
        'NON_MAPPATO', 'NON_MAPPATO_BILLOO_PROMO_NON_SUFFICIENTE', 'CONFLITTO_SUBCHANNEL_PROMO'
    ])].copy()
    excluded = df[df['Esito mapping'].str.contains('MODELLO_NON_ATTIVO', na=False)].copy()
    duplicate_supply = df['ID fornitura'].ne('') & df.duplicated('ID fornitura', keep=False)
    anomalies = df[
        df['Data sottoscrizione'].isna()
        | df['Segmento'].isna()
        | df['Point of Delivery'].eq('')
        | ((df['Stato'] != 'ANNULLATO') & df['Data attivazione'].isna())
        | (df['Data chiusura'].notna() & df['Data attivazione'].isna())
        | (df['Data chiusura'].notna() & (df['Data chiusura'] < df['Data attivazione']))
        | duplicate_supply
        | df['Stato'].isin(['IN ATTESA', 'SOSPESO'])
    ].copy()

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
        f'Partner con modello non attivo: **{len(excluded)}** | '
        f'Anomalie dati: **{len(anomalies)}** | '
        f'Configurazioni incomplete: **{len(invalid_configs)}** | '
        f'Malus della competenza: **{len(malus_new)}**'
    )

    export = to_excel({
        'Sintesi partner': summary,
        'Movimenti': movements,
        'Gettoni iniziali': initial,
        'Annullamenti': cancelled,
        'Ricorrenti': recurring,
        'Malus del mese': malus_new,
        'Non mappati': unmapped,
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
