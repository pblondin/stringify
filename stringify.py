#!/usr/bin/env python3

# system imports
import argparse
import io
import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Dependency imports
import gspread
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage


class NotFoundException(Exception):
    pass


class Mode:
    EXPORT_ALL = "export_all"
    EXPORT_ANDROID = "export_android"
    EXPORT_IOS = "export_ios"
    IMPORT_ANDROID = "import_android"
    IMPORT_IOS = "import_ios"


class TranslationRow:
    def __init__(self, key):
        self.key = key
        self.translations = dict()

    def add_translation(self, lang, value):
        self.translations.update({lang: value})

    def get_translation(self, lang):
        return self.translations.get(lang)


class Dictionary:
    def __init__(self):
        self.dictionary = dict()
        self.languages = set()

    def add_translation(self, key, lang, word, comment=None):
        self.languages.add(lang)
        translation_row = self.dictionary.get(key)
        if translation_row is None:
            translation_row = TranslationRow(key)
            self.dictionary.update({translation_row.key: translation_row})

        translation_row.add_translation(lang, word)

    def get_translation(self, key, lang):
        return self.dictionary.get(key).get_translation(lang)

    def keys_iterator(self):
        return self.dictionary

    def keys(self):
        return self.dictionary.keys()


# CONTENT PARSERS

class Command:
    def execute(self):
        pass


class GoogleDocsHandler(Command):
    def __init__(self, credentials_path):
        self.client = None
        self.credentials_path = credentials_path

    def _oauth_load_credentials(self):
        log_step("Loading saved credentials")
        if os.path.isfile(settings[SETTINGS_KEY_CREDENTIALS_LOCATION]):
            try:
                storage = Storage(settings[SETTINGS_KEY_CREDENTIALS_LOCATION])
                return storage.locked_get()
            except:
                return None
        return None

    def _oauth_save_credentials(self, credentials):
        log_step("Saving credentials")
        storage = Storage(G_FILE)
        storage.locked_put(credentials)

    def _oauth(self):
        log_step("Authorizing user")
        credentials = self._oauth_load_credentials()
        if credentials:
            return credentials
        else:
            flow = OAuth2WebServerFlow(client_id=G_CLIENT_ID,
                                       client_secret=G_CLIENT_SECRET,
                                       scope=G_SCOPE,
                                       redirect_uri=G_REDIRECT)
            auth_uri = flow.step1_get_authorize_url()
            print(auth_uri)
            code = input("Enter code:")
            credentials = flow.step2_exchange(code)
            self._oauth_save_credentials(credentials)
            return credentials

    def authorize(self):
        if not self.client:
            credentials = self._oauth()
            self.client = gspread.authorize(credentials)
        return self.client

    def write(self, google_doc_name, dictionary):
        google_doc_client = self.authorize()
        try:
            spreadsheet = google_doc_client.open(google_doc_name).sheet1
        except gspread.SpreadsheetNotFound:
            spreadsheet = google_doc_client.create(google_doc_name).sheet1

        log_step("Clear spreadsheet...")
        self._clear_worksheet(spreadsheet)
        log_step("Writing cells...")

        row = 1
        languages = dictionary.languages
        languages = sorted(languages)
        for index, lang in enumerate(languages):
            column = index + 2
            log_step("language ({}{}): {}".format(row, column, lang))
            spreadsheet.update_cell(row, column, lang)

        row = 2
        for key in dictionary.keys():
            spreadsheet.update_cell(row, 1, key)
            for index, lang in enumerate(languages):
                column = index + 2
                translated_value = dictionary.get_translation(key, lang)
                spreadsheet.update_cell(row, column, translated_value)
                log_step("cell ({}{}): {}".format(row, column, translated_value))
            row += 1

    def read(self, google_doc_name):
        pass

    def _clear_worksheet(self, spreadsheet):
        '''This is way more efficient than worksheet.clear() method'''
        cells = spreadsheet.findall(re.compile(".+"))
        for cell in cells:
            cell.value = ""

        spreadsheet.update_cells(cells)


class DataLoader(Command):
    def execute(self):
        raise NotImplemented

    def load(self):
        return self.execute()


class GoogleDocDataLoader(DataLoader):
    def __init__(self, google_docs):
        self.sheet = google_docs.sheet1

        pass

    def execute(self):
        pass


class AndroidStringsLoader(DataLoader):
    def __init__(self, path, **kwargs):
        self.path = path
        self.filename = kwargs['xml_name'] if 'xml_name' in kwargs.keys() else 'strings.xml'
        self.default_language = kwargs['default_language'] if 'default_language' in kwargs.keys() else 'en'

    def execute(self):
        file_paths = find_files(path=self.path, filename_regex=self.filename)
        dictionary = Dictionary()
        for filepath in file_paths:
            language = self._decode_filepath_language(filepath)
            entries = self._decode_file_entries(filepath)

            if len(language.strip()) == 0:
                language = self.default_language

            for entry in entries:
                dictionary.add_translation(entry[0], language, entry[1])
        return dictionary

    def _decode_filepath_language(self, filepath):
        match = re.match(r'.*values([-a-z]{0,3})', filepath)
        if match:
            postfix = match.group(1)
            if len(postfix) == 3:
                postfix = postfix[-2:]
        return postfix

    def _decode_file_entries(self, filepath):
        entries = []
        xml = ET.parse(filepath)
        root = xml.getroot()
        for child in root:
            key = child.get('name')
            value = child.text
            entries.append((key, value))
        return entries


class IOSStringsLoader(DataLoader):
    def __init__(self, path, **kwargs):
        self.path = path
        self.filename = kwargs['filename'] if 'filename' in kwargs.keys() else 'Localizable.strings'

    def execute(self):
        filepaths = find_files(path=self.path, filename_regex=self.filename)
        dictionary = Dictionary()

        for filepath in filepaths:
            language = self._decode_filepath_language(filepath)
            entries = self._decode_file_entries(filepath)

            for key, word in entries:
                dictionary.add_translation(key, language, word)

        return dictionary

    def _decode_filepath_language(self, path):
        match = re.match(r"""(.*)\.lproj""", path)
        if match:
            prefix = match.group(1)
            if len(prefix) > 2:
                prefix = prefix[-2:]
            return prefix
        else:
            raise NotFoundException

    def _decode_file_entries(self, filepath):
        entries = []
        file = open(filepath)

        for line in file:
            match = re.match(r'"(.*)".*=.*"(.*)";', line)
            if match:
                entries.append((match.group(1), match.group(2)))
        return entries


# PRODUCERS
class Producer(Command):
    def execute(self):
        pass


class AndroidProducer(Producer):
    def __init__(self, parser):
        pass

    def execute(self):
        pass


class SwiftProducer(Producer):
    def __init__(self, parser):
        pass

    def execute(self):
        pass


APP_NAME = "stringify"
APP_VERSION = "0.0.3"

SETTINGS_KEY_GDOC_NAME = "spreadsheet_name"
SETTINGS_KEY_DEFAULT_LANG = "default_language"
SETTINGS_KEY_EXPORT_PATH = "locale"
SETTINGS_KEY_XML_NAME = "xml_name"
SETTINGS_KEY_MODE = "mode"
SETTINGS_KEY_LOGS_ON = "logs_on"
SETTINGS_KEY_CREDENTIALS_LOCATION = "credentials_location"

SETTINGS_DEFAULT_LANG = "en"
SETTINGS_DEFAULT_MODE = Mode.EXPORT_ALL
SETTINGS_DEFAULT_XML_NAME = "strings.xml"
SETTINGS_DEFAULT_LOGS_ON = True

settings = dict()

G_CLIENT_ID = '463196519538-07lgrq1rim3mie9p8tnc9rl06o18di9g.apps.googleusercontent.com'
G_CLIENT_SECRET = 'Je8slGzLy8kVUXRHcN5fXCJ2'
G_SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
G_REDIRECT = 'http://localhost/'
G_FILE = ".credentials"


def log_exception(message, force_quit=False):
    print("EXCEPTION: {}".format(message))
    if force_quit:
        sys.exit()


def log_step(message):
    if settings[SETTINGS_KEY_LOGS_ON]:
        pass
    print("[stringify]:\t{}".format(message))


def log_version():
    log_step("version: " + APP_VERSION)
    log_step("-----------------")
    log_step("")


def decode_sys_args():
    global settings

    settings.update({SETTINGS_KEY_DEFAULT_LANG: SETTINGS_DEFAULT_LANG})
    settings.update({SETTINGS_KEY_MODE: SETTINGS_DEFAULT_MODE})
    settings.update({SETTINGS_KEY_XML_NAME: SETTINGS_DEFAULT_XML_NAME})
    settings.update({SETTINGS_KEY_LOGS_ON: SETTINGS_DEFAULT_LOGS_ON})
    settings.update({SETTINGS_KEY_EXPORT_PATH: '.'})
    settings.update({SETTINGS_KEY_CREDENTIALS_LOCATION: G_FILE})

    parser = argparse.ArgumentParser(description='Stringify parser')
    parser.add_argument("-d", "--default-lang", help="Android default language")
    parser.add_argument("-n", "--spreadsheet-name", help="Google Spreadsheet name")
    parser.add_argument("-p", "--dest-path", help="Localized strings destination path")
    parser.add_argument("-x", "--xml-filename", help="Android xml name. Default: strings.xml")
    parser.add_argument("-m", "--mode",
                        help="Available modes: "
                             "export_ios - exports ios strings,\n"
                             "export_android - exports android strings,\n"
                             "import_android - import Android strings and create Google Spreadsheet,\n"
                             "import_ios - import iOS strings and create Google Spreadsheet,\n"
                             "export_all (default) - exports both Android and iOS\n")
    parser.add_argument("-o", "--logs-off", help="Turns progress logs off")
    parser.add_argument("-u", "--oauth-credentials-location", help="Directory to save/load oauth credentials")

    args = parser.parse_args()

    if args.mode:
        settings.update({SETTINGS_KEY_MODE: args.mode.lower()})

    if args.spreadsheet_name:
        settings.update({SETTINGS_KEY_GDOC_NAME: args.spreadsheet_name})
    else:
        log_exception("'Spreadsheet name' shouldn't be empty", force_quit=True)

    if args.default_lang:
        settings.update({SETTINGS_KEY_DEFAULT_LANG: args.default_lang})

    if args.dest_path:
        settings.update({SETTINGS_KEY_EXPORT_PATH: args.dest_path})

    if args.xml_filename:
        settings.update({SETTINGS_KEY_XML_NAME: args.xml_filename})

    if args.logs_off:
        settings.update({SETTINGS_KEY_LOGS_ON, False})

    if args.oauth_credentials_location:
        settings.update({SETTINGS_KEY_CREDENTIALS_LOCATION: args.oauth_credentials_location})


# todo use os.walk instead?
def find_files(path='.', filename_regex=None):
    found_files = []
    for filename in os.listdir(path):
        filepath = os.path.join(path, filename)
        if os.path.isdir(filepath):
            list = find_files(filepath, filename_regex)
            found_files.extend(list)
        elif os.path.isfile(filepath):
            if filename_regex and filename.startswith(filename_regex):
                found_files.append(filepath)
            elif filename_regex is None:
                found_files.append(filepath)

    return found_files


def load_languages(sheet):
    log_step("Reading languages")
    column = 2
    languages = []
    while True:
        lang_code = sheet.cell(1, column).value
        if len(lang_code.strip()) > 0:
            languages.append(lang_code)
            column += 1
        else:
            return languages


def read_row(sheet, row, langs_count):
    row_data = list()
    for column in range(1, langs_count + 2):
        cell_value = sheet.cell(row, column).value
        if len(cell_value.strip()) == 0 and column == 1:
            return row_data
        else:
            row_data.append(cell_value)
    return row_data


def read_strings(sheet, langs_count):
    log_step("Reading spreadsheet cells")
    row = 2
    rows = []
    empty_row = False
    while True:
        row_data = read_row(sheet, row, langs_count)
        if len(row_data) == 0:
            if empty_row:
                return rows
            else:
                empty_row = True
        else:
            empty_row = False

        rows.append(row_data)
        row += 1


def save_file(content, dir_name, file_name):
    log_step("Saving file {}/{}".format(dir_name, file_name))
    cwd = os.getcwd()
    try:
        os.mkdir(dir_name)
    except Exception:
        pass

    try:
        os.chdir(dir_name)
    except Exception:
        pass

    file = open(file_name, "w")
    file.write(content)
    file.close()
    os.chdir(cwd)


def export_android(languages, strings,
                   export_path=None,
                   default_language=SETTINGS_DEFAULT_LANG,
                   xml_file_name=SETTINGS_DEFAULT_XML_NAME):
    log_step("Exporting Android strings")
    cwd = os.getcwd()
    if export_path:
        try:
            os.makedirs(export_path, exist_ok=True)
        except Exception:
            pass
        os.chdir(export_path)

    for i, lang in enumerate(languages):
        xml = ET.Element('resources')
        for row in strings:
            if len(row) == 0:
                continue
            string_row = ET.SubElement(xml, 'string')
            string_row.set('name', row[0])
            string_row.text = row[i + 1]

        dom = minidom.parseString(ET.tostring(xml, 'utf-8'))
        pretty_dom = dom.toprettyxml()

        dir_name = "values".format(default_language) if default_language == lang else "values-{}".format(lang)
        save_file(pretty_dom, dir_name, xml_file_name)

    os.chdir(cwd)


def export_ios(languages, strings, export_path=None):
    log_step("Exporting iOS strings")
    cwd = os.getcwd()
    if export_path:
        try:
            os.makedirs(export_path, exist_ok=True)
        except:
            pass

        os.chdir(export_path)

    for i, lang in enumerate(languages):
        output = io.StringIO()
        for row in strings:
            if len(row) == 0:
                continue
            output.write('"{}" = "{}";\n'.format(row[0], row[i + 1]))

        language_dir = "{}.lproj".format(lang)
        save_file(output.getvalue(), language_dir, "Localizable.strings")

    os.chdir(cwd)


def handle_export(mode, gdoc_name):
    book = gc.open(gdoc_name)
    sheet = book.sheet1

    languages = load_languages(sheet)
    strings = read_strings(sheet, len(languages))

    if mode in (Mode.EXPORT_ANDROID, Mode.EXPORT_ALL):
        export_android(languages,
                       strings,
                       settings[SETTINGS_KEY_EXPORT_PATH],
                       settings[SETTINGS_KEY_DEFAULT_LANG],
                       settings[SETTINGS_KEY_XML_NAME])

    if mode in (Mode.EXPORT_IOS, Mode.EXPORT_ALL):
        export_ios(languages, strings, settings[SETTINGS_KEY_EXPORT_PATH])


def main():
    decode_sys_args()
    log_version()
    credentials_location = settings[SETTINGS_KEY_CREDENTIALS_LOCATION]
    mode = settings[SETTINGS_KEY_MODE]

    google_doc_name = settings[SETTINGS_KEY_GDOC_NAME]
    google_docs_handler = GoogleDocsHandler(credentials_location)

    if mode == Mode.IMPORT_ANDROID:
        AndroidProducer().execute()
    if mode == Mode.IMPORT_IOS:
        SwiftProducer().execute()
    if mode in (Mode.EXPORT_IOS, Mode.EXPORT_ANDROID):
        path = settings[SETTINGS_KEY_EXPORT_PATH]
        xml_name = settings[SETTINGS_KEY_XML_NAME]
        default_language = settings[SETTINGS_KEY_DEFAULT_LANG]

        if mode == Mode.EXPORT_ANDROID:
            loader = AndroidStringsLoader(path=path, xml_name=xml_name, default_language=default_language)

        if mode == Mode.EXPORT_IOS:
            loader = IOSStringsLoader(path=path, filename=xml_name)

        dictionary = loader.load()
        google_docs_handler.write(google_doc_name, dictionary)
    log_step("Done")


if __name__ == '__main__':
    main()
