#  _____    _ _ _              ____             __ _
# | ____|__| (_) |_ ___  _ __ / ___|___  _ __  / _(_) __ _
# |  _| / _` | | __/ _ \| '__| |   / _ \| '_ \| |_| |/ _` |
# | |__| (_| | | || (_) | |  | |__| (_) | | | |  _| | (_| |
# |_____\__,_|_|\__\___/|_|   \____\___/|_| |_|_| |_|\__, |
#                                                    |___/
from sublime import View
from sublime_plugin import EventListener, TextCommand

from os import path, sep
from re import match, split

LINE_ENDINGS = {
	'cr': 'cr',
	'crlf': 'windows',
	'lf': 'unix'
}

CHARSETS = {
	'latin1': 'Western (ISO 8859-1)',
	'utf-16be': 'UTF-16 BE',
	'utf-16le': 'UTF-16 LE',
	'utf-8': 'UTF-8',
}

DEBUG = True


def debug(x: str):
	if DEBUG:
		print('EditorConfig: ' + x)


class EditorConfig(EventListener):
	def on_load(self, view: View):
		dispatch(view, '_load_')

	def on_activated(self, view: View):
		dispatch(view, '_start_')

	def on_pre_save(self, view: View):
		dispatch(view, '_save_')


def dispatch(view: View, event: str):
	parts = path.split(view.file_name())
	config = parse_file(find_file(parts[0]), parts[1].split('.')[-1])

	if event == '_start_' or event == '_load_':
		fix_eol(view, config.get('end_of_line'))
		fix_charset(view, config.get('charset'))

	if event == '_save_':
		fix_indent(view, config.get('indent_style'))
		fix_newline(view, config.get('insert_final_newline'))


class RemoveFinalNewlinesCommand(TextCommand):
	def run(self, edit):
		region = self.view.find('\n*\0', 0)
		if region.size() > 1:
			self.view.erase(edit, region)
			debug('Remove final newlines')


class NormalizeFinalNewlinesCommand(TextCommand):
	def run(self, edit):
		region = self.view.find('\n*\0', 0)
		if region.size() > 1:
			self.view.replace(edit, region, '\n')
			debug('Normalize final newlines')


# ---------------------------------------------------------------------------- #


def fix_charset(view: View, charset: str):
	encoding = view.encoding()
	if (
		encoding != 'Undefined' and
		charset in CHARSETS and
		CHARSETS[charset] != encoding
	):
		new_encoding = CHARSETS[charset]
		view.set_encoding(new_encoding)
		debug('Updated charset from ' + encoding + ' to ' + new_encoding)


def fix_eol(view: View, eol: str):
	if eol in LINE_ENDINGS and LINE_ENDINGS[eol] != view.line_endings().lower():
		view.set_line_endings(LINE_ENDINGS[eol])
		debug('Updated EOL')


def fix_indent(view: View, indent_style: str):
	spaces = view.settings().get('translate_tabs_to_spaces')
	if indent_style == 'space' and spaces is False:
		view.run_command('expand_tabs', {'set_translate_tabs': True})
		debug('Update Using spaces')
	elif indent_style == 'tab' and spaces is True:
		view.run_command('unexpand_tabs', {'set_translate_tabs': True})
		debug('Update Using tabs')


def fix_newline(view: View, insert_final_newline: str):
	ensure_newline_at_eof_on_save = view.settings().get('ensure_newline_at_eof_on_save')
	if insert_final_newline == 'true' or ensure_newline_at_eof_on_save:
		view.run_command('normalize_final_newlines')
	else:
		view.run_command('remove_final_newlines')


# ---------------------------------------------------------------------------- #


def find_file(root: str) -> str:
	file = path.join(root, '.editorconfig')
	if not path.exists(file):
		parent = path.split(root)[0]
		return '' if parent == root else find_file(parent)
	return file


def parse_file(file: str, extension: str) -> dict:
	options = {}
	if file:
		applicable = False
		for line in get_lines(file):
			if line[0] == '[':
				applicable = matches(line[1:-1], extension)
				continue
			if not applicable:
				continue
			if '=' in line:
				option, value = split(' *= *', line, 1)
				options[option] = value
	return options


def get_lines(file: str) -> list:
	lines = []
	for line in open(file).readlines():
		if line.strip():
			lines.append(split('[#;]', line)[0].strip().lower())
	return lines


def matches(pattern: str, extension: str) -> bool:
	pattern = clean_pattern(pattern)
	for part in pattern.split(','):
		if part is '*' or part is extension:
			return True
	return False


def clean_pattern(pattern: str) -> str:
	if pattern is '*':
		return pattern
	clean = ''
	for char in pattern:
		if match('[a-z,-]', char):
			clean += char
	return clean
