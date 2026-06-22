import logging
import re
from copy import deepcopy
from pathlib import Path
from datetime import datetime
import pandas as pd
import xml.etree.ElementTree as ET
from lib_utilys import clean_special_characters, read_json

logger = logging.getLogger(__name__)

def rename_detail_columns(df: pd.DataFrame):
    rename_map = {
        'EAN': 'EAN_UPC',
        'Material_number_vendor': 'VEND_MAT',
        'Material_number': 'MATERIAL',
        'Position_number': 'PO_ITEM',
        'Delivery_date': 'DELIV_DATE',
        'Discount': 'DISCOUNT',
        'Quantity': 'QUANTITY',
        'Material_description_vendor': 'SHORT_TEXT',
        'Price_unit': 'PRICE_UNIT',
        'Product_line_price': 'NET_VALUE',
        'Product_net_price': 'NET_PRICE',
        'Product_price': 'GROS_PRICE',
        'Purchase_order_line': 'PO_NUMBER',
        'Purchase_order_line_date': 'PO_DATE',
        'Unit': 'UNIT',
        'Vendor_position_number': 'VEND_PO_ITEM',
    }
    return df.rename(columns=rename_map)

def rename_header_columns(df: pd.DataFrame):
    rename_map = {
        'Creditor_number': 'CREDITOR',
        'Partner_name': 'CRED_NAME',
        'Partner_street': 'CRED_STREET',
        'Partner_city': 'CRED_CITY',
        'Partner_postal_code': 'CRED_POSTAL',
        'Partner_country': 'CRED_CNTRY',
        'Partner_tax_number': 'CRED_TAX_NUM',
        'IBAN': 'CRED_IBAN',
        'BIC': 'CRED_BIC',
        'Creditor_international_location_number': 'CRED_ILN',
        'Invoice_number': 'INVOICE',
        'Invoice_date': 'INVO_DATE',
        'Debtor_number': 'DEBTOR',
        'Debtor_name': 'DEB_NAME',
        'Debtor_street': 'DEB_STREET',
        'Debtor_city': 'DEB_CITY',
        'Debtor_postal_code': 'DEB_POSTAL',
        'Purchase_order': 'PO_NUMBER',
        'Purchase_order_date': 'PO_DATE',
        'Vendor_order': 'CRED_ORDER',
        'Net_value': 'NET_VALUE',
        'Invoice_value': 'INVO_VALUE',
        'Total_tax' : 'TAX_VALUE',
        'Tax_percent': 'TAX_PERCENT',
        'Delivery_date': 'DELIV_DATE',
        'Term_discount': 'TERM_DISC',
        'Payment_term_with_discount_days': 'PAYM_TERM_DISC',
    }
    return df.rename(columns=rename_map)

def check_type(df: pd.DataFrame):
    """Checks the type of the invoice."""
    if df['INVO_VALUE'].iloc[0] == 0:
        df['TYPE'] = 'NULL'
    elif df['INVO_VALUE'].iloc[0] < 0:
        df['TYPE'] = 'CRME'
    elif df['INVO_VALUE'].iloc[0] > 0:
        df['TYPE'] = 'INVO'
    return df

def prop_po_number_over_rows(df_header: pd.DataFrame, df_details: pd.DataFrame):
    """Propogates po numbers over rows missing them."""
    prev_po_number = None
    header_has_po = df_header['PO_NUMBER'].notnull().any()
    header_po = df_header['PO_NUMBER'].iloc[0] if header_has_po else None
    for idx, row in df_details.iterrows():
        po_number_line = row.get('PO_NUMBER')
        if pd.isna(po_number_line) and header_has_po:
            df_details.loc[idx, 'PO_NUMBER'] = header_po
            po_number_line = header_po
        elif pd.isna(po_number_line) and prev_po_number is not None:
            df_details.loc[idx, 'PO_NUMBER'] = prev_po_number
            po_number_line = prev_po_number
        prev_po_number = po_number_line
        if pd.isna(po_number_line):
            raise MissingValueError(f"PO_NUMBER is missing for line {idx} and cannot be propogated from header or previous lines.")
    return df_details

def add_time_keys(df: pd.DataFrame):
    """Adds time-related key-value pairs to the dataframe."""
    df['CREATE_DATE'] = datetime.now().strftime('%Y%m%d')
    df['CREATE_TIME'] = datetime.now().strftime('%H%M%S')
    df['TIMESTAMP'] = datetime.now().strftime('%Y%m%d%H%M%S')
    return df

def add_debtor_info(df: pd.DataFrame, debmap_pth: Path):
    """Configures the debtor code based on the debtor name."""
    deb_map = read_json(debmap_pth)
    df['DEB_CODE'] = df['DEB_NAME'].apply(lambda x: deb_map.get(x, {}).get('debtor_code'))
    if df['DEB_CODE'].isnull().any():
        raise MissingValueError("Debtor code is None for some rows.")
    df['DEB_ILN'] = df['DEB_NAME'].apply(lambda x: deb_map.get(x, {}).get('illnr'))
    df['DEBTOR'] = df['DEBTOR'].apply(lambda x: clean_special_characters(x) if pd.notnull(x) else x)
    df['INVOICE'] = df['INVOICE'].apply(lambda x: clean_special_characters(x) if pd.notnull(x) else x)
    return df

def add_creditor_info(df: pd.DataFrame, ctryabbr_path: Path):
    """Configures the creditor number based on the partner country."""
    ctry_map = read_json(ctryabbr_path)
    df['CREDITOR'] = df.apply(
        lambda row: ctry_map.get(row['CRED_CNTRY'], {}).get('creditor_number')
        if pd.notnull(row['CRED_CNTRY']) and isinstance(row['CREDITOR'], dict)
        else row['CREDITOR'],
        axis=1,
    )
    if df['CREDITOR'].isnull().any():
        raise MissingValueError("Creditor number is None for some rows.")
    return df

def parse_country(df: pd.DataFrame, ctryabbr_path: Path):
    """Parses the partner country and configures it based on the country abbreviation mapping."""
    ctry_map = read_json(ctryabbr_path)
    df['CRED_CNTRY'] = df['CRED_CNTRY'].apply(lambda x: ctry_map.get(x) if pd.notnull(x) else x)
    if df['CRED_CNTRY'].isnull().any():
        raise MissingValueError("Partner country is None for some rows.")
    return df

def configure_pdf_filename(df: pd.DataFrame):
    """Configures the PDF filename based on certain key-value pairs."""
    df['PDF_FILENAME'] = df.apply(lambda row: f"{row['CREDITOR']}-{row['DEB_ILN']}.{row['INVOICE']}.pdf" if pd.notnull(row['CREDITOR']) and pd.notnull(row['DEB_ILN']) and pd.notnull(row['INVOICE']) else None, axis=1)
    df['PDF_FILENAME'] = df['PDF_FILENAME'].apply(lambda x: clean_special_characters(x) if pd.notnull(x) else x)
    return df

def configure_xml_filename(df: pd.DataFrame):
    """Configures the XML filename based on certain key-value pairs."""
    df['XML_FILENAME'] = df.apply(lambda row: f"{row['CREDITOR']}-{row['DEB_ILN']}.{row['INVOICE']}.xml" if pd.notnull(row['CREDITOR']) and pd.notnull(row['DEB_ILN']) and pd.notnull(row['INVOICE']) else None, axis=1)
    df['XML_FILENAME'] = df['XML_FILENAME'].apply(lambda x: clean_special_characters(x) if pd.notnull(x) else x)
    return df

def configure_tax_qualifier(df: pd.DataFrame, EUabbr_path: Path, taxmap_path: Path):
    """Configures the tax for the invoice based on the partner country and tax percent."""
    eu_countries = read_json(EUabbr_path).get('EU_country_abbreviations', [])
    def get_tax_qualifier(row):
        tax_percent = row.get('TAX_PERCENT')
        if pd.isnull(tax_percent):
            if pd.isnull(row.get('TAX_VALUE')):
                tax_percent = 0
            else:
                tax_percent = round(row.get('INVO_VALUE') / row.get('NET_VALUE', 1) - 1, 2) * 100
        if row['CRED_CNTRY'] == 'NL':
            return read_json(taxmap_path).get('NL', {}).get(str(int(tax_percent)))
        elif row['CRED_CNTRY'] in eu_countries:
            return read_json(taxmap_path).get('EU', {}).get(str(int(tax_percent)))
        else:
            return read_json(taxmap_path).get('Non-EU', {}).get(str(int(tax_percent)))
    df['TAX_QUALIFIER'] = df.apply(get_tax_qualifier, axis=1)
    if df['TAX_QUALIFIER'].isnull().any():
        raise MissingValueError("Tax qualifier is None for some rows.")
    return df

def configure_crme(df_header: pd.DataFrame, df_details: pd.DataFrame):
    """Configures the CRME type of invoice."""
    df_header['INVO_VALUE'] = df_header['INVO_VALUE'].astype(str).str.replace('-', '')
    df_header['NET_VALUE'] = df_header['NET_VALUE'].astype(str).str.replace('-', '')
    df_header['TOTAL_TAX'] = df_header['TOTAL_TAX'].astype(str).str.replace('-', '')
    if not df_details.empty:
        df_details[0]['Quantity'] = str(df_details[0]['Quantity']).replace('-', '')

def populate_header(df_header: pd.DataFrame, root: ET.Element):
    """Replaces [KEY] placeholders in the STARTSEG subtree with header values."""
    header_values = df_header.iloc[0].to_dict()
    for elem in root.iter():
        if elem.text and elem.text.startswith("[") and elem.text.endswith("]"):
            key = elem.text[1:-1]
            value = header_values.get(key)
            if pd.notnull(value):
                elem.text = str(value)
        
def populate_details(df_details: pd.DataFrame, root: ET.Element, node: ET.Element):
    """Clones the E1EDP01 template for each detail row and replaces placeholders."""
    root.remove(node)
    for _, row in df_details.iterrows():
        detail_line = deepcopy(node)
        row_values = row.to_dict()
        for elem in detail_line.iter():
            if elem.text and elem.text.startswith("[") and elem.text.endswith("]"):
                key = elem.text[1:-1]
                value = row_values.get(key)
                if pd.notnull(value):
                    elem.text = str(value)
        root.append(detail_line)

def remove_placeholders(root: ET.Element):
    """Removes elements whose text is still a [PLACEHOLDER]."""
    placeholder_re = re.compile(r"^\[[^\]]+\]$")
    for parent in root.iter():
        for child in list(parent):
            if child.text and placeholder_re.match(child.text.strip()):
                parent.remove(child)

class Invoice:
    def __init__(self, uid: str, adress: str, message: str, business: str, subject: str, text: str, pdf: bytes):
        self.uid = uid
        self.adress = adress
        self.message = message
        self.business = business
        self.subject = subject
        self.text = text
        self.pdf = pdf
        self.pdf_filename = None
        self.kvpairs = None
        self.type = None

    def configure_kvpairs(self, kv_pairs: dict):
        """Configures key-value pairs for the invoice."""
        self.kvpairs = kv_pairs
        self.check_type_()
        self.set_line_level_()

    def check_type_(self):
        """Checks the type of the invoice."""
        if self.kvpairs['Invoice_value'] == 0:
            self.type = 'NULL'
            self.kvpairs['TYPE'] = 'NULL'
        elif self.kvpairs['Invoice_value'] < 0:
            self.type = 'CRME'
            self.kvpairs['TYPE'] = 'CRME'
        elif self.kvpairs['Invoice_value'] > 0:
            self.type = 'INVO'
            self.kvpairs['TYPE'] = 'INVO'

    def additional_kv_pairs(self,debmap_pth: Path, ctryabbr_path: Path, taxmap_path: Path, EUabbr_path: Path):
        """Adds additional key-value pairs to the invoice."""
        self.kvpairs['Creation_date'] = datetime.now().strftime('%Y%m%d')
        self.kvpairs['Creation_time'] = datetime.now().strftime('%H%M%S')
        self.kvpairs['Timestamp'] = datetime.now().strftime('%Y%m%d%H%M%S')
        self.kvpairs['Debtor_code'] = (read_json(debmap_pth)).get(self.kvpairs['Debtor_name'], {}).get('debtor_code')
        if self.kvpairs['Debtor_code'] is None: raise MissingValueError("Debtor code is None")
        self.kvpairs['Debtor_international_location_number'] = (read_json(debmap_pth)).get(self.kvpairs['Debtor_name'], {}).get('illnr')
        self.kvpairs['Partner_country'] = (read_json(ctryabbr_path)).get(self.kvpairs['Partner_country'])
        if self.kvpairs['Partner_country'] is None: raise MissingValueError("Partner country is None")
        if isinstance(self.kvpairs['Creditor_number'], dict): self.kvpairs['Creditor_number'] = self.kvpairs['Creditor_number'].get(f'{self.kvpairs["Partner_country"]}')
        self.kvpairs['Invoice_number'] = clean_special_characters(self.kvpairs['Invoice_number'])
        if 'Debtor_number' in self.kvpairs and self.kvpairs['Debtor_number'] is not None: self.kvpairs['Debtor_number'] = clean_special_characters(self.kvpairs['Debtor_number'])
        self.pdf_filename = f"{self.kvpairs['Creditor_number']}-{self.kvpairs['Debtor_international_location_number']}.{self.kvpairs['Invoice_number']}.pdf"
        self.pdf_filename = clean_special_characters(self.pdf_filename)
        self.configure_tax_(EUabbr_path, taxmap_path)

    def set_line_level_(self):
        """Sets certain key-value pairs to line level in Material_list."""
        if self.kvpairs['Material_list']:
            previous_pol = None
            for line in self.kvpairs.get('Material_list'):
                Purchase_order_line = line.get('Purchase_order_line', None)
                if Purchase_order_line is None and self.kvpairs.get('Purchase_order') is not None:
                    line['Purchase_order_line'] = self.kvpairs.get('Purchase_order')
                if previous_pol is not None and Purchase_order_line is None and self.kvpairs.get('Purchase_order') is None:
                    line['Purchase_order_line'] = previous_pol
                previous_pol = line.get('Purchase_order_line', None)
                if Purchase_order_line is None and self.kvpairs.get('Purchase_order') is None and previous_pol is None:
                    raise MissingValueError("Purchase order is None")

    def configure_crme(self):
        """Configures the CRME type of invoice."""
        try:
            self.kvpairs['Invoice_value'] = str(self.kvpairs['Invoice_value']).replace('-', '')
            self.kvpairs['Net_value'] = str(self.kvpairs['Net_value']).replace('-', '')
            self.kvpairs['Total_tax'] = str(self.kvpairs['Total_tax']).replace('-', '')
            if self.kvpairs['Material_list']:
                self.kvpairs['Material_list'][0]['Quantity'] = str(self.kvpairs['Material_list'][0]['Quantity']).replace('-', '')
        except Exception as e:
            self.Output.output(f"Error configuring CRME: {e}")

    def configure_tax_(self, EUabbr_path: Path, taxmap_path: Path):
        """Configures the tax for the invoice."""
        eu_countries = (read_json(EUabbr_path)).get('EU_country_abbreviations', [])
        tax_percent = self.kvpairs.get('Tax_percent', None)
        if tax_percent is None:
            # Assumption that if no tax percent is given and no total tax is given, the tax percent is 0
            if self.kvpairs.get('Total_tax', None) is None:
                tax_percent = 0
                self.kvpairs['Tax_percent'] = tax_percent
            else:
                tax_percent = round(self.kvpairs.get('Invoice_value') / self.kvpairs.get('Net_value', 1) - 1, 2) * 100
                self.kvpairs['Tax_percent'] = tax_percent
        if self.kvpairs['Partner_country'] == 'NL':
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('NL', {}).get(str(int(tax_percent)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")
        elif self.kvpairs['Partner_country'] in eu_countries:
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('EU', {}).get(str(int(tax_percent)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")
        else:
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('Non-EU', {}).get(str(int(tax_percent)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")

class MissingValueError(Exception):
    """Custom exception for missing or None values."""
    def __init__(self, message="Required value is missing or None"):
        self.message = message
        super().__init__(self.message)

        



    