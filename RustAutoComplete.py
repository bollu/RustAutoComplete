import os
import sublime
import sublime_plugin
import platform
import re
import subprocess
import tempfile
from subprocess import Popen, PIPE

settings = None


class Settings:

    def __init__(self):
        package_settings = sublime.load_settings("RustAutoComplete.sublime-settings")
        package_settings.add_on_change("racer", settings_changed)
        package_settings.add_on_change("search_paths", settings_changed)

        self.racer_bin = package_settings.get("racer", "racer")
        self.search_paths = package_settings.get("search_paths", [])
        self.package_settings = package_settings

    def unload(self):
        self.package_settings.clear_on_change("racer")
        self.package_settings.clear_on_change("search_paths")


def plugin_loaded():
    global settings
    settings = Settings()


def plugin_unloaded():
    global settings
    if settings != None:
        settings.unload()
        settings = None


def settings_changed():
    global settings
    if settings != None:
        settings.unload()
        settings = None
    settings = Settings()


class Result:

    def __init__(self, parts):
        self.completion = parts[0]
        self.snippet = parts[1]
        self.row = int(parts[2])
        self.column = int(parts[3])
        self.path = parts[4]
        self.type = parts[5]
        self.context = parts[6]


def expand_all(paths):
    return [os.path.expanduser(path)
            for path in paths]


def determine_save_dir(view):
    # If we return None then it will fall back on the system tmp directory
    save_dir = None

    # Try to save to the same directory the file is saved in
    if view.file_name() is not None:
        save_dir = os.path.dirname(view.file_name())
    
    # If the file has not been saved, and the window has a folder open,
    # try to treat the main folder as if it were a cargo project
    source_folder = ""
    if len(view.window().folders()) > 0:
        source_folder = os.path.join(view.window().folders()[0], "src")
    if save_dir is None and os.path.isdir(source_folder):
        save_dir = source_folder

    # If nothing else has worked, look at the folders that other open files are in
    if save_dir is None:
        paths = [view.file_name() for view in view.window().views() if view.file_name() is not None]
        # We only care about open rust files
        paths = [path for path in paths if path[-3:] == ".rs"]
        directories = [os.path.dirname(path) for path in paths]
        if len(directories) == 0:
            return None

        # Count the frequency of occurance of each path
        dirs = {}
        for item in directories:
            if item not in dirs:
                dirs[item] = 1
            else:
                dirs[item] += 1

        # Use the most common path
        save_dir = max(dirs.keys(), key=(lambda key: dirs[key]))

    return save_dir


def run_racer(view, cmd_list):
    # Retrieve the entire buffer
    region = sublime.Region(0, view.size())
    content = view.substr(region)
    with_snippet = cmd_list[0] == "complete-with-snippet"

    # Figure out where to save the temp file so that racer can do
    # autocomplete based on other user files
    save_dir = determine_save_dir(view)
    print(save_dir)

    # Save that buffer to a temporary file for racer to use
    temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, dir=save_dir)
    temp_file_path = temp_file.name
    temp_file.write(content)
    temp_file.close()
    cmd_list.insert(0, settings.racer_bin)
    cmd_list.append(temp_file_path)

    # Copy the system environment and add the source search
    # paths for racer to it
    expanded_search_paths = expand_all(settings.search_paths)
    env_path = ":".join(expanded_search_paths)
    env = os.environ.copy()
    env['RUST_SRC_PATH'] = env_path

    # Run racer
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    #debug
    #print(" ".join(cmd_list))
    
    process = Popen(cmd_list, stdout=PIPE, env=env, startupinfo=startupinfo)
    (output, err) = process.communicate()
    exit_code = process.wait()

    # Remove temp file
    os.remove(temp_file_path)

    # Parse results
    results = []
    match_string = "MATCH "
    if exit_code == 0:
        for byte_line in output.splitlines():
            line = byte_line.decode("utf-8")
            if line.startswith(match_string):
                if with_snippet:
                    parts = line[len(match_string):].split(';', 7)
                else:
                    parts = line[len(match_string):].split(',', 6)
                    parts.insert(1, "")

                result = Result(parts)
                if result.path == view.file_name():
                    continue
                if result.path == temp_file_path:
                    result.path = view.file_name()
                results.append(result)
    else:
        print("failed: exit_code:", exit_code, output)
    return results

def parse_results(view, raw_output, with_snippet):
    results = []
    match_string = "MATCH "
    for line in raw_output.splitlines():
        if line.startswith(match_string):
            if with_snippet:
                parts = line[len(match_string):].split(';', 7)
            else:
                parts = line[len(match_string):].split(',', 6)
                parts.insert(1, "")
                print("parts = ", parts)

            result = Result(parts)
            if result.path == view.file_name():
                continue
            if result.path == "TODO: take the temp file path":#temp_file_path:
                result.path = "TODO: TAKE TEMP FILE PATH" #view.file_name()
            results.append(result)

    return results


def racer_ffi_complete_with_snippet(view, row, col):
    import ctypes

    save_dir = determine_save_dir(view)
    #print(save_dir)

    region = sublime.Region(0, view.size())
    content = view.substr(region)
    
    # Save that buffer to a temporary file for racer to use
    temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, dir=save_dir)
    temp_file_path = temp_file.name
    temp_file.write(content)
    temp_file.close()

    #HACK - modify environ variable
    #expanded_search_paths = expand_all(settings.search_paths)
    #env_path = ":".join(expanded_search_paths)
    #os.environ['RUST_SRC_PATH'] = env_path

    #call the ffi and return the string
    out_string = ctypes.create_string_buffer("++EMPTY STRING BUFFER++".encode('utf-8'), 500000)

    libracer = ctypes.CDLL("/home/bollu/prog/racer/target/libracer-lib-a4b9b29f855e0068.so")

    libracer.complete_with_snippet_ffi(row, col, temp_file_path.encode('utf-8'), out_string)
    os.remove(temp_file_path)

    #put the result into multiprocessing
    return out_string.value.decode("utf-8")


def racer_ffi_find_defintion(view, row, col):
    import ctypes

    save_dir = determine_save_dir(view)
    #print(save_dir)

    region = sublime.Region(0, view.size())
    content = view.substr(region)
    
    # Save that buffer to a temporary file for racer to use
    temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=True, dir=save_dir)
    temp_file_path = temp_file.name
    temp_file.write(content)
    #temp_file.close()


    #HACK - modify environ variable
    #expanded_search_paths = expand_all(settings.search_paths)
    #env_path = ":".join(expanded_search_paths)
    #os.environ['RUST_SRC_PATH'] = env_path

    #call the ffi and return the string
    out_string = ctypes.create_string_buffer("++EMPTY STRING BUFFER++".encode('utf-8'), 500000)
    libracer = ctypes.CDLL("/home/bollu/prog/racer/target/libracer-lib-a4b9b29f855e0068.so")
        
    libracer.find_definition_ffi(row, col, temp_file_path.encode('utf-8'), out_string)
    temp_file.close()
    os.remove(temp_file_path)

    return str(out_string.value.decode("utf-8"))


class RustAutocomplete(sublime_plugin.EventListener):

    def on_query_completions(self, view, prefix, locations):
        # Check if this is a Rust source file. This check
        # relies on the Rust syntax formatting extension
        # being installed - https://github.com/jhasse/sublime-rust
        if view.match_selector(locations[0], "source.rust"):
            # Get the buffer location in correct format for racer
            row, col = view.rowcol(locations[0])
            row += 1

            raw_results = None

            try:
                print("trying to autocomplete")
                #raw_results = run_racer(view, ["complete-with-snippet", str(row), str(col)])
                raw_results = racer_ffi_complete_with_snippet(view, row, col)
                print("raw result: ", raw_results)
                raw_results = parse_results(view, raw_results, with_snippet=True)
                #raw_results = raw_results.decode('utf-8')
                #print("string: ", raw_results)

            except FileNotFoundError:
                print("Unable to find racer executable (check settings)")
                return

            results = []
            lalign = 0;
            ralign = 0;
            for result in raw_results:
                result.middle = "{0} ({1})".format(result.type, os.path.basename(result.path))
                lalign = max(lalign,len(result.completion)+len(result.middle))
                ralign = max(ralign, len(result.context))

            for result in raw_results:
                context = result.context
                result = "{0} {1:>{3}} : {2:{4}}".format(result.completion, result.middle, result.context, lalign - len(result.completion), ralign), result.snippet
                results.append(result)
            if len(results) > 0:
                # return list(set(results))
                return (list(set(results)),
                        sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)



class RustGotoDefinitionCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        # Get the buffer location in correct format for racer
        row, col = self.view.rowcol(self.view.sel()[0].begin())
        row += 1

        raw_results = racer_ffi_complete_with_snippet(self.view, row, col)
        raw_results = parse_results(self.view, raw_results, with_snippet=False)

        if len(results) == 1:
            result = results[0]
            path = result.path
            # On Windows the racer will return the paths without the drive
            # letter and we need the letter for the open_file to work.
            if platform.system() == 'Windows' and not re.compile('^\w\:').match(path):
                path = 'c:' + path
            encoded_path = "{0}:{1}:{2}".format(path, result.row, result.column)
            self.view.window().open_file(encoded_path, sublime.ENCODED_POSITION)

