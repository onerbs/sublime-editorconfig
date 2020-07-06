#  _____    _ _ _              ____             __ _
# | ____|__| (_) |_ ___  _ __ / ___|___  _ __  / _(_) __ _
# |  _| / _` | | __/ _ \| '__| |   / _ \| '_ \| |_| |/ _` |
# | |__| (_| | | || (_) | |  | |__| (_) | | | |  _| | (_| |
# |_____\__,_|_|\__\___/|_|   \____\___/|_| |_|_| |_|\__, |
#                                                    |___/

import sublime
import sublime_plugin

from os import path, sep

LINE_ENDINGS = {
    'cr'   : 'cr',
    'crlf' : 'windows',
    'lf'   : 'unix'
}

CHARSETS = {
    'latin1'    : 'Western (ISO 8859-1)',
    'utf-16be'  : 'UTF-16 BE',
    'utf-16le'  : 'UTF-16 LE',
    'utf-8'     : 'UTF-8',
}

DEBUG = True
def debug(x):
    if DEBUG:
        print(x)

class EditorConfig(sublime_plugin.EventListener):
    def on_load(self, view):
        dispatch('_load_', view)

    def on_activated(self, view):
        dispatch('_start_', view)

    def on_pre_save(self, view):
        dispatch('_save_', view)


class RemoveFinalNewlinesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        region = self.view.find('\n*\Z', 0)
        if region.size() > 1:
            self.view.erase(edit, region)
            debug('Remove final newlines')

class NormalFinalNewlinesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        region = self.view.find('\n*\Z', 0)
        if region.size() > 1:
            self.view.replace(edit, region, '\n')
            debug('Normalize final newlines')

#------------------------------------------------------------------------------#

def dispatch(event, view):
    file_name = view.file_name()
    config = _mkconfig(file_name)

    if not config:
        return

    if event == '_start_' or event == '_load_':
        charset = config.get('charset')
        encoding = view.encoding()
        if (
            encoding != 'Undefined' and
            charset in CHARSETS and
            CHARSETS[charset] != encoding
        ):
            new_encoding = CHARSETS[charset]
            view.set_encoding(new_encoding)
            debug('Updated charset from '+encoding+' to '+new_encoding)

        eol = config.get('end_of_line')
        if eol in LINE_ENDINGS and LINE_ENDINGS[eol] != view.line_endings().lower():
            view.set_line_endings(LINE_ENDINGS[eol])
            debug('Updated EOL')

        indent_style = config.get('indent_style')
        spaces = view.settings().get('translate_tabs_to_spaces')
        if indent_style == 'space' and spaces == False:
            view.run_command('expand_tabs', {'set_translate_tabs': True})
            debug('Update Using spaces')
        elif indent_style == 'tab' and spaces == True:
            view.run_command('unexpand_tabs', {'set_translate_tabs': True})
            debug('Update Using tabs')

    if event == '_save_':
        insert_final_newline = config.get('insert_final_newline')
        ensure_newline_at_eof_on_save = view.settings().get('ensure_newline_at_eof_on_save')
        if insert_final_newline == 'true' or ensure_newline_at_eof_on_save:
            view.run_command('normal_final_newlines')
        else:
            view.run_command('remove_final_newlines')


def _mkconfig(file_name):
    if None == file_name:
        return False
    folder, file = path.split(file_name)
    config = parse_file(folder, file)

    # Set indent_size to "tab" if indent_size is unspecified and
    # indent_style is set to "tab".
    if config.get("indent_style") == "tab" and not "indent_size" in config:
        config["indent_size"] = "tab"

    # Set tab_width to indent_size if indent_size is specified and
    # tab_width is unspecified
    if ("indent_size" in config and "tab_width" not in config and
            config["indent_size"] != "tab"):
        config["tab_width"] = config["indent_size"]

    # Set indent_size to tab_width if indent_size is "tab"
    if ("indent_size" in config and "tab_width" in config and
            config["indent_size"] == "tab"):
        config["indent_size"] = config["tab_width"]

    return config

#------------------------------------------------------------------------------#

from re import match, split

def parse_file(file_path, file_name):

    ec_file = path.join(file_path, '.editorconfig')

    if not path.exists(ec_file):
        prent_path = path.dirname(file_path)
        return dict(editorconfig='None') if prent_path == file_path else parse_file(prent_path, file_name)

    with open(ec_file) as f:
        lines = list(map(lambda s: s.lower().strip(), f.readlines()))

    aplicable = False
    optname = None
    options = dict(editorconfig=ec_file)

    for line in lines:
        # comment or blank line?
        if line == '' or line[0] in '#;':
            continue

        # is it a section header?
        if line[0] == '[':
            pattern = line[1:-1]
            aplicable = fnmatch(file_name, pattern)
            continue

        if not aplicable:
            continue

        if '=' in line:
            optname, optval = list(map(lambda s: s.strip(), line.split('=', 2)))
            if match(' [#;]', optval):
                optval = split(' [#;]', optval)[0]
            # allow empty values
            if optval == '""':
                optval = ''

            options[optname] = optval

    return options


def fnmatch(name, pattern):
    pattern = clean_pattern(pattern)
    name = name.split('.')[-1]
    for p in pattern.split(','):
        if p == '*' or name == p:
            return True
    return False


def clean_pattern(p):
    if p == '*':
        return p
    r = ''
    for c in p:
        if match('[a-z,-]', c):
            r = r + c
    return r
