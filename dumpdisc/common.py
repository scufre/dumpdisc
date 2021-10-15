# Copyright (c) 2021, scufre
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import struct

def _unpack(format, data):
	result = ()
	while len(format) > 0:
		if format[0] in (">", "<"):
			current_format = format[0]
			format = format[1:]
		else:
			current_format = ""
		while len(format) > 0 and not format[0] in (">", "<"):
			current_format = current_format + format[0]
			format = format[1:]
		
		current_size = struct.calcsize(current_format)
		current_data = data[:current_size]
		data = data[current_size:]
		result = result + struct.unpack(current_format, current_data)
		
	if len(data) != 0:
		raise ValueError("remaining data to unpack")
		
	return result
	
class Dumpeable(object):
	_TAB = "    "

	def dump(self, indent=0):
		raise NotImplementedError
		
	def __str__(self):
		return self.dump()

class FileSystem(object):
	@property
	def partitions(self):
		raise NotImplementedError
		
class Partition(object):
	@property
	def type(self):
		raise NotImplementedError
	
	@property
	def label(self):
		raise NotImplementedError
	
	@property
	def root_directory(self):
		raise NotImplementedError

class File(Dumpeable):
	@property
	def name(self):
		raise NotImplementedError
		
	@property
	def streams(self):
		raise NotImplementedError
	
	def get_content(self, stream=0):
		raise NotImplementedError
		
class Directory(Dumpeable):
	@property
	def name(self):
		raise NotImplementedError

	@property
	def directories(self):
		raise NotImplementedError
		
	@property
	def files(self):
		raise NotImplementedError
