#  _____    _ _ _              ____             __ _
# | ____|__| (_) |_ ___  _ __ / ___|___  _ __  / _(_) __ _
# |  _| / _` | | __/ _ \| '__| |   / _ \| '_ \| |_| |/ _` |
# | |__| (_| | | || (_) | |  | |__| (_) | | | |  _| | (_| |
# |_____\__,_|_|\__\___/|_|   \____\___/|_| |_|_| |_|\__, |
#                                                    |___/
from sublime import View, Settings, load_settings
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

settings = None
config = None


def debug(msg, tag="EditorConfig"):
    settings["debug"] and print("%s: %s" % (tag, msg) if tag else msg)


def verbose(msg: str):
    settings["verbose"] and print("  %s" % msg)


# -----------------------------------------------------------------------------


class EditorConfig(EventListener):
    def on_activated(self, view: View):
        dispatch(view, "load")

    def on_pre_save(self, view: View):
        dispatch(view, "save")


def dispatch(view: View, event: str):
    file_path = view.file_name()
    if not file_path: return

    settings = use_settings()
    if event in settings["watch"]:
        debug("---- %s %s ----" % (event, file_path), tag=None)
        fixes = Fixes(view, file_path)
        for fix in settings["on_" + event]:
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
    def __init__(self, view: View, file_path: str):
        self.view = view
        self.config = parse_config(file_path)
        self.table = {
            "encoding":      self.encoding,
            "eol":           self.eol,
            "final_newline": self.final_newline,
            "indent":        self.indent,
        }

    def encoding(self):
        # encoding = config["encoding"]
        # curr_encoding = self.v
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
        end_of_line = self.config["end_of_line"]
        line_endings = "crlf" if self.view.line_endings().lower() == "windows" else "lf"
        if end_of_line != line_endings:
            self.view.set_line_endings(LINE_ENDINGS[end_of_line])
            debug("Using %s" % end_of_line)

    def final_newline(self):
        if self.config["insert_final_newline"]:
            self.view.run_command("normalize_final_newlines")
        else:
            self.view.run_command("remove_final_newlines")

    def indent(self):
        indent_style = self.config["indent_style"]
        indent_size = self.config["indent_size"]
        self.view.settings().set("tab_size", indent_size)
        if self.view.find("^\t", 0).size() > 0:
            # verbose("Detect: tab")
            # self.view.settings().set("tab_size", indent_size)
            # debug("Using tab size %s" % indent_size)
            if indent_style == "space":
                self.view.run_command("expand_tabs", {"set_translate_tabs": True})
                debug("Using spaces")
        else:
            re_spaces = "^ {%s}" % indent_size
            if self.view.find(re_spaces, 0).size() > 0:
                # verbose("Detect: space")
                if indent_style == "tab":
                    self.view.run_command("unexpand_tabs", {"set_translate_tabs": True})
                    debug("Using tabs")
            else:
                # verbose("No indentation detected")
                pass


# -----------------------------------------------------------------------------


def parse_config(file_path: str) -> dict:
    """
    Basic INI parser.
    """
    config = use_config()
    config_file = lookup(file_path)
    if config_file is None:
        return config
    lines = get_lines(config_file)
    extension = path.split(file_path)[1].split(".")[-1]
    applies = False
    for line in lines:
        if line.startswith("["):
            applies = matches(extension, line[1:-1])
            # verbose("%s %s %s" %(extension, applies, line))
        elif applies and "=" in line:
            option, value = re.split(r"\s*=\s*", line, 1)
            config[option] = parse_value(value)
    return inspect('Parsed (%s)' % extension, config)


def parse_value(value: str):
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except:
        return value


def lookup(root_dir: str) -> str:
    """
    Look for the .editorconfig file in the root_dir.

    If the file is not found, then lookup in the parent
    directory recursively until reach the root directory.

    :return: The path to the file if found, else an empty string.
    """
    parent = path.split(root_dir)[0]
    if parent == root_dir:
        debug("not found.")
        return None
    file_path = path.join(parent, ".editorconfig")
    if path.exists(file_path):
        debug("using " + file_path)
        return file_path
    return lookup(parent)


def get_lines(file_name: str) -> list:
    """
    Ignore empty lines and comments, output in lowercase.
    """
    lines = []
    for ln in open(file_name).readlines():
        line = re.split("[#;]", ln)[0].strip()
        if line:
            # verbose('  %s' % line)
            lines.append(line)
    return lines


def matches(string: str, line: str) -> bool:
    """
    Check whether a string matches a pattern or not.
    """
    for pattern in get_patterns(line):
        if pattern == "*" or pattern == string:
            return True
        elif pattern.endswith("*"):
            return string.startswith(pattern[:-1])
        elif pattern.startswith("*"):
            return string.endswith(pattern[1:])
        else:
            return string == pattern
    return False


def get_patterns(source: str) -> list:
    if source == "*":
        return [source]
    elif "{" in source:
        return re.findall(r"\*\.{(\S+)}", source)[0].split(",")
    else:
        return [source[2:]]


# -----------------------------------------------------------------------------


def use_settings() -> dict:
    global settings
    if settings is not None:
        return settings

    # Load default settings
    memory = load_settings("EditorConfig.sublime-settings")
    settings = {}
    for key, fallback in [
        ("debug",   False),
        ("verbose", False),
        ("watch",   []),
        ("on_load", []),
        ("on_save", []),
    ]:
        value = memory.get(key)
        # verbose("key: %s, value: %s" % (key, value))
        settings[key] = fallback if value is None else value
    verbose('Settings: ' % settings)
    return settings


def use_config() -> dict:
    global config
    if config is not None:
        return config

    raw = load_settings("Preferences.sublime-settings")
    system = {
        "default_encoding": raw.get("default_encoding").lower(),
        "default_line_ending": get_default_line_ending(raw),
        "tab_size": raw.get("tab_size"),
        "translate_tabs_to_spaces": raw.get("translate_tabs_to_spaces"),
        "ensure_newline_at_eof_on_save": raw.get("ensure_newline_at_eof_on_save"),
        "trim_trailing_white_space_on_save": raw.get("trim_trailing_white_space_on_save"),
    }
    config = {
        "charset": system.get("default_encoding"),
        "end_of_line": system.get("default_line_ending"),
        "indent_size": system.get("tab_size"),
        "indent_style": "space" if system.get("translate_tabs_to_spaces") else "tab",
        "insert_final_newline": system.get("ensure_newline_at_eof_on_save"),
        "trim_trailing_whitespace": system.get("trim_trailing_white_space_on_save"),
    }
    return inspect('Config', config)


def get_default_line_ending(raw: Settings) -> str:
    from sublime import platform
    ending = raw.get("default_line_ending").lower()
    is_windows = ending == "system" and platform() == "windows"
    is_windows = ending == "windows" or is_windows
    return "crlf" if is_windows else "lf"


def inspect(title: str, data: dict) -> dict:
    if settings["verbose"]:
        content = "%s: {\n" % title
        for key, value in data.items():
            content += "  %s: %s\n" % (key, value)
        print("%s}" % content)
    return data
