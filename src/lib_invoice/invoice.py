import logging
from pathlib import Path
from datetime import datetime
from lib_utilys import clean_special_characters, read_json

logger = logging.getLogger(__name__)

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
            self.kvpairs['Type'] = 'NULL'
        elif self.kvpairs['Invoice_value'] < 0:
            self.type = 'CRME'
            self.kvpairs['Type'] = 'CRME'
        elif self.kvpairs['Invoice_value'] > 0:
            self.type = 'INVO'
            self.kvpairs['Type'] = 'INVO'

    def additional_kv_pairs(self, crit_path: Path, debmap_pth: Path, ctryabbr_path: Path, taxmap_path: Path, EUabbr_path: Path):
        """Adds additional key-value pairs to the invoice."""
        logger.debug("Received the following parameters: \n %s \n %s \n %s \n %s \n %s", crit_path, debmap_pth, ctryabbr_path, taxmap_path, EUabbr_path)
        self.kvpairs['Creation_date'] = datetime.now().strftime('%Y%m%d')
        self.kvpairs['Creation_time'] = datetime.now().strftime('%H%M%S')
        self.kvpairs['Timestamp'] = datetime.now().strftime('%Y%m%d%H%M%S')
        logger.debug(read_json(crit_path))
        logger.debug(self.kvpairs["Debtor_name"])
        self.kvpairs['Debtor_code'] = (read_json(crit_path)).get(self.kvpairs['Debtor_name'], {}).get('debtor_code')
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
        if self.kvpairs['Partner_country'] == 'NL':
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('NL', {}).get(str(int(self.kvpairs['Tax_percent'] if self.kvpairs['Tax_percent'] is not None else 0)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")
        elif self.kvpairs['Partner_country'] in eu_countries:
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('EU', {}).get(str(int(self.kvpairs['Tax_percent'] if self.kvpairs['Tax_percent'] is not None else 0)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")
        else:
            self.kvpairs['Tax_qualifier'] = (read_json(taxmap_path)).get('Non-EU', {}).get(str(int(self.kvpairs['Tax_percent'] if self.kvpairs['Tax_percent'] is not None else 0)))
            if self.kvpairs['Tax_qualifier'] is None: raise MissingValueError("Tax qualifier is None")

class MissingValueError(Exception):
    """Custom exception for missing or None values."""
    def __init__(self, message="Required value is missing or None"):
        self.message = message
        super().__init__(self.message)

        



    