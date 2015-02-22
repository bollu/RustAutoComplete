#!/usr/bin/env python3
import ctypes

#call the ffi and return the string
out_string = ctypes.create_string_buffer("++EMPTY STRING BUFFER++".encode('utf-8'), 500000)
print("created out string")

libracer = ctypes.CDLL("/home/bollu/prog/racer/target/libracer-lib-a4b9b29f855e0068.so")
print("loaded DLL")

temp_file_path = "/home/bollu/tmp/main.rs";
libracer.complete_with_snippet_ffi(1, 9, temp_file_path.encode('utf-8'), out_string)
print("out string bytes: ", out_string, "\nstring: |\n", out_string.value)
