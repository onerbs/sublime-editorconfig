#  _____    _ _ _              ____             __ _
# | ____|__| (_) |_ ___  _ __ / ___|___  _ __  / _(_) __ _
# |  _| / _` | | __/ _ \| '__| |   / _ \| '_ \| |_| |/ _` |
# | |__| (_| | | || (_) | |  | |__| (_) | | | |  _| | (_| |
# |_____\__,_|_|\__\___/|_|   \____\___/|_| |_|_| |_|\__, |
#                                                    |___/
from sublime import View, load_settings
from sublime_plugin import EventListener, TextCommand
from os import path
import re

LINE_ENDINGS = {
    "cr":   "cr",
    "crlf": "windows",
    "lf":   "unix"
}

ENCODING = {
    "latin1":   "Western (ISO 8859-1)",
    "utf-16be": "UTF-16 BE",
    "utf-16le": "UTF-16 LE",
    "utf-8":    "UTF-8",
}


class Holder:
    def __init__(self):
        self._props = []

    def __setitem__(self, key, value):
        if key not in self._props:
            self._props.append(key)
        object.__setattr__(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def __str__(self):
        data = '\n'.join('  %s: %s' % (k, self[k]) for k in self._props)
        return '{\n%s\n}' % data


class Config:
    def __init__(self, raw):
        self._holder = Holder()
        for key, fallback in [
            # Default configuration
            ('debug',   False),
            ('verbose', False),
            ('watch',   []),
            ('on_load', []),
            ('on_save', []),
        ]:
            self._holder[key] = raw.get(key) or fallback

    def __getattr__(self, key):
        return self._holder[key]

    def __getitem__(self, key):
        return self._holder[key]

    def __str__(self):
        return str(self._holder)


def debug(msg, tag="EditorConfig"):
    config.debug and print("%s: %s" % (tag, msg) if tag else msg)


def verbose(msg, tag=" >> "):
    config.verbose and print("%s: %s" % (tag, msg) if tag else msg)


config = Config(load_settings("EditorConfig.sublime-settings"))


# -----------------------------------------------------------------------------


class EditorConfig(EventListener):
    def on_activated(self, view: View):
        dispatch(view, "load")

    def on_pre_save(self, view: View):
        dispatch(view, "save")


def dispatch(view: View, event: str):
    file_name = view.file_name()
    if not file_name: return

    if event in config.watch:
        debug("---- %s %s ----" % (event, file_name), tag=None)
        fixes = Fixes(view, parse_file(file_name))
        for fix in config["on_" + event]:
            fixes.table[fix]()


class RemoveFinalNewlinesCommand(TextCommand):
    def run(self, edit):
        region = self.view.find(r"\n*\Z", 0)
        if region.size() > 1:
            self.view.erase(edit, region)
            debug("Final newlines removed")


class NormalizeFinalNewlinesCommand(TextCommand):
    def run(self, edit):
        region = self.view.find(r"\n*\Z", 0)
        if region.size() > 1:
            self.view.replace(edit, region, "\n")
            debug("Final newlines normalized")


# -----------------------------------------------------------------------------


class Fixes:
    def __init__(self, view, settings):
        self.view = view
        self.settings = settings
        self.table = {
            "encoding":      self.encoding,
            "eol":           self.eol,
            "final_newline": self.final_newline,
            "indent":        self.indent,
        }

    def encoding(self):
        # encoding = config.get("encoding")
        # curr_encoding = self.view.encoding()
        # if (
        #     encoding != "Undefined" and
        #     encoding in ENCODING and
        #     ENCODING[encoding] != encoding
        # ):
        #     new_encoding = ENCODING[encoding]
        #     view.set_encoding(new_encoding)
        #     debug("Updated encoding from " + encoding + " to " + new_encoding)
        debug('TODO implement encoding fix')

    def eol(self):
        eol = self.settings.get("end_of_line")
        curr_eol = self.view.line_endings().lower()
        if eol in LINE_ENDINGS and LINE_ENDINGS[eol] != curr_eol:
            self.view.set_line_endings(LINE_ENDINGS[eol])
            debug("Updated EOL")

    def final_newline(self):
        insert_fnl = self.settings.get("insert_final_newline")
        ensure_fnl = self.view.settings().get("ensure_newline_at_eof_on_save")
        if insert_fnl == "true" or ensure_fnl:
            self.view.run_command("normalize_final_newlines")
        else:
            self.view.run_command("remove_final_newlines")

    def indent(self):
        indent_style = self.settings.get("indent_style")
        indent_size = int(self.settings.get("indent_size", "0"))
        tab_size = self.view.settings().get("tab_size")
        if self.view.find("^\t", 0).size() > 0:
            # view using tabs
            if indent_size != tab_size:
                self.view.settings().set("tab_size", indent_size)
            if indent_style == "space":
                self.view.run_command("expand_tabs", {"set_translate_tabs": True})
                debug("Using spaces")
        else:
            curr_tab_size = self.view.settings().get("tab_size")
            tab_size = indent_size if indent_size > 0 else curr_tab_size
            spaces_pattern = "^ {" + str(tab_size) + "}"
            if self.view.find(spaces_pattern, 0).size() > 0:
                # view using spaces
                if indent_style == "tab":
                    self.view.run_command("unexpand_tabs", {"set_translate_tabs": True})
                    debug("Using tabs")
            else:
                # view without indentation
                pass


# -----------------------------------------------------------------------------


def parse_file(absolute_path: str) -> dict:
    """Very basic INI parser."""

    # todo: read from sublime settings
    options = {
        'indent_size': 2
    }
    config_file = lookup(absolute_path)
    if not config_file:
        return options
    extension = path.split(absolute_path)[1].split(".")[-1]
    applicable = False
    for line in get_lines(config_file):
        if line.startswith("["):
            applicable = matches(extension, line[1:-1])
            continue
        if not applicable:
            continue
        if "=" in line:
            option, value = re.split(r"\s*=\s*", line, 1)
            options[option] = value
    if config.verbose:
        times = max(len(it) for it in options.keys()) + 2
        for key, val in options.items():
            spaces = " " * (times - len(key))
            print("  %s%s%s" % (key, spaces, val))
    return options


def lookup(root_dir: str) -> str:
    """
    Look for the .editorconfig file from the provided directory.

    If the file is not in the provided path, then lookup in the
    parent of the provided directory.

    :return: The path to the file if found, else an empty string.
    """
    parent = path.split(root_dir)[0]
    if parent == root_dir:
        debug("not found.")
        return ""
    file_path = path.join(parent, ".editorconfig")
    if path.exists(file_path):
        debug("found: " + file_path)
        return file_path
    return lookup(parent)


def get_lines(filename: str) -> list:
    """Ignore empty lines and comments and transform lo lowercase."""
    lines = []
    with open(filename) as file:
        for line in file.readlines():
            ln = re.split("[#;]", line)[0].strip().lower()
            if ln:
                lines.append(ln)
                verbose(ln)
    return lines


def matches(string: str, _pattern: str) -> bool:
    """Check whether a string matches a pattern or not"""
    for pattern in extract_patterns(_pattern):
        if pattern == "*" or pattern == string:
            return True
        elif pattern.endswith("*"):
            return string.startswith(pattern[:-1])
        elif pattern.startswith("*"):
            return string.endswith(pattern[1:])
    return False


def extract_patterns(source: str) -> list:
    if source == "*":
        return [source]
    elif "{" in source:
        return re.findall(r"\*\.{(\S+)}", source)[0].split(",")
    else:
        return [source[2:]]
