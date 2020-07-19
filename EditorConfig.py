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

LOAD = 'load'
SAVE = 'save'


class Config():
	# TODO use st config
	debug = False
	watch = [LOAD, SAVE]
	# on_load = []
	# on_save = []


def debug(message: str, tag='EditorConfig'):
	if Config.debug:
		tag = tag + ': ' if tag else ''
		print(tag + message)


class EditorConfig(EventListener):
	def on_activated(self, view: View):
		dispatch(view, LOAD)

	def on_pre_save(self, view: View):
		dispatch(view, SAVE)


def dispatch(view: View, event: str):
	file_name = view.file_name()
	if file_name and event in Config.watch:
		parts = path.split(file_name)
		debug('---- ' + event + ' ' + parts[1] + ' ----', tag=None)
		config = parse_file(walk(parts[0]), parts[1].split('.')[-1])

		if event == LOAD:
			# fix_charset(view, config.get('charset'))
			fix_eol(view, config.get('end_of_line'))
			fix_indent(view, config.get('indent_style'), int(config.get('indent_size', '0')))

		if event == SAVE:
			fix_newline(view, config.get('insert_final_newline'))


class RemoveFinalNewlinesCommand(TextCommand):
	def run(self, edit):
		region = self.view.find('\n*\Z', 0)
		if region.size() > 1:
			self.view.erase(edit, region)
			debug('Remove final newlines')


class NormalizeFinalNewlinesCommand(TextCommand):
	def run(self, edit):
		region = self.view.find('\n*\Z', 0)
		if region.size() > 1:
			self.view.replace(edit, region, '\n')
			debug('Normalize final newlines')

# ---------------------------------------------------------------------------- #


def fix_charset (view: View, charset: str):
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


def fix_indent(view: View, indent_style: str, indent_size: int):
	if view.find('^\t', 0).size() > 0:
		# view using tabs
		if indent_style == 'space':
			view.run_command('expand_tabs', {'set_translate_tabs': True})
			debug('Using spaces')
	else:
		tab_size = indent_size if indent_size > 0 else view.settings().get('tab_size')
		spaces_pattern = '^ {' + str(tab_size) + '}'
		if view.find(spaces_pattern, 0).size() > 0:
			# view using spaces
			if indent_style == 'tab':
				view.run_command('unexpand_tabs', {'set_translate_tabs': True})
				debug('Using tabs')
		else:
			# view without indentation
			pass


def fix_newline(view: View, insert_final_newline: str):
	ensure_newline_at_eof_on_save = view.settings().get('ensure_newline_at_eof_on_save')
	if insert_final_newline == 'true' or ensure_newline_at_eof_on_save:
		view.run_command('normalize_final_newlines')
	else:
		view.run_command('remove_final_newlines')


# ---------------------------------------------------------------------------- #


def walk(root: str) -> str:
	file = path.join(root, '.editorconfig')
	if not path.exists(file):
		parent = path.split(root)[0]
		file = '' if parent == root else walk(parent)
	debug('found: ' + file)
	return file


def parse_file(file: str, extension: str) -> dict:
	options = {}
	if file:
		applicable = False
		for line in get_lines(file):
			if line.startswith('['):
				applicable = matches(line[1:-1], extension)
				continue
			if not applicable:
				continue
			if '=' in line:
				option, value = split(' *= *', line, 1)
				options[option] = value
	# if Config.debug:
	#   for key in options.keys():
	#       val = options[key]
	#       times = 7 - len(val)
	#       print('  ' + val + repeat(' ', times) + key)
	return options


# def repeat(s: str, t: int) -> str:
#   if t <= 0:
#       return ''
#   if t == 1:
#       return s
#   else:
#       r = s
#       for _ in range(1, t):
#           r += s
#       return r


def get_lines(file: str) -> list:
	lines = []
	for line in open(file).readlines():
		if line.strip():
			lines.append(split('[#;]', line)[0].strip().lower())
	# if Config.debug:
	#   for line in lines:
	#       print(line)
	return lines


def matches(pattern: str, extension: str) -> bool:
	pattern = clean_pattern(pattern)
	for part in pattern.split(','):
		if part == '*' or part == extension:
			return True
	return False


def clean_pattern(pattern: str) -> str:
	result = ''
	if pattern is '*':
		pattern, result = result, pattern
	for char in pattern:
		if match('[a-z,-]', char):
			result += char
	# debug('pattern: ' + result)
	return result
