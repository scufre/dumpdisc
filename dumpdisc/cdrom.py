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

# Based on:
# https://github.com/claunia/edccchk/blob/master/edccchk.c
# See also:
# https://gist.github.com/murachue/b52ded0b7968e870b6a310d439ddcb30
# https://psx-spx.consoledev.net/cdromdrive/#cdrom-sector-encoding

class EDC(object):
	def __init__(self):
		self.__table = [0 for i in range(256)]
		for i in range(256):
			edc = i
			for j in range(8):
				edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)		
			self.__table[i] = edc
			
	def compute(self, data):
		edc = 0
		for b in data:
			edc = (edc >> 8) ^ self.__table[(edc ^ b) & 0xff]
		return edc
		
class ECC(object):
	def __init__(self):
		self._f_table = [0 for i in range(256)]
		self._b_table = [0 for i in range(256)]
		for i in range(256):
			j = (i << 1) ^ (0x11d if i & 0x80 else 0)
			self._f_table[i] = j
			self._b_table[i ^ j] = i
			
	def _compute_pq(self, data, major_count, minor_count, major_mult, minor_inc):
		result = bytearray(b"\x00" * major_count * 2)
		size = major_count * minor_count
		for major in range(major_count):
			index = (major >> 1) * major_mult + (major & 1)
			ecc_a = 0
			ecc_b = 0
			for minor in range(minor_count):
				temp = data[index]
				index += minor_inc
				if index >= size:
					index -= size
				ecc_a ^= temp
				ecc_b ^= temp
				ecc_a = self._f_table[ecc_a]
			ecc_a = self._b_table[self._f_table[ecc_a] ^ ecc_b]
			result[major] = ecc_a
			result[major + major_count] = ecc_a ^ ecc_b
		return result

	def compute(self, data):
		p_parity = self._compute_pq(data, 86, 24, 2, 86)
		q_parity = self._compute_pq(data + p_parity, 52, 43, 86, 88)
		return p_parity + q_parity
