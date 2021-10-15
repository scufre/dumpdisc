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

import argparse
import os
import traceback
import dumpdisc
import dumpdisc.image
import dumpdisc.common

def tree(partition):
	print("> {} ({})".format(partition.label, partition.type))
	pending = [(entry, 1) for entry in partition.root_directory.directories + partition.root_directory.files]
	while len(pending) > 0:
		entry, depth = pending.pop(0)
		
		print("{}{} {}".format(" " * 4 * depth, "+" if isinstance(entry, dumpdisc.common.Directory) else "-", entry.name))
		
		if isinstance(entry, dumpdisc.common.Directory):
			pending[0:0] = map(lambda e: (e, depth + 1), entry.directories + entry.files)

parser = argparse.ArgumentParser(description="Extract the files of all filesystems found in a disc image")
group = parser.add_mutually_exclusive_group()
group.add_argument('-r' '--rawimage', help="Treat specified image file as a RAW image file (2352 bytes/sector)", dest="rawimage", action="store_true", default=False, required=False)
group.add_argument('-m' '--ddrmap', help="Use specified ddrescue map file (not valid for raw images)", dest="ddrmap", type=str, required=False)
parser.add_argument('-b' '--badmap', help="Use specified file with bad sectors", dest="badmap", type=str, required=False)
group = parser.add_mutually_exclusive_group()
group.add_argument('-s', '--start', help="Data track start sector (useful when the image is of a whole mixed CD)", type=int, dest="start", required=False, default=0)
group.add_argument('-o', '--offset', help="Image base sector offset (useful when the image is of the data portion of a mixed CD)", type=int, dest="offset", required=False, default=0)
parser.add_argument('image', help="Image file name", type=str)
args = parser.parse_args()

f = open(args.image, "rb")
start = 0
cls = dumpdisc.image.RawCDImage if args.rawimage else dumpdisc.image.ISOImage
image = cls(f)
if args.offset != 0:
	image = dumpdisc.image.OffsetedImage(image, args.offset)
	start = args.offset
if args.badmap != None:
	image = dumpdisc.image.ImageWithBadMap(image, args.badmap)
if args.ddrmap != None:
	image = dumpdisc.image.DDRescueImage(image, args.ddrmap)
if args.start != 0:
	start = args.start
	
with image:
	disc = dumpdisc.Disc(image, start)
	for partition in disc.partitions:
		print(partition.dump())
		pending = [(partition.root_directory, 1), ]
		while len(pending) > 0:
			entry, depth = pending.pop(0)
			print(entry.dump(depth))
			if isinstance(entry, dumpdisc.common.Directory):
				pending[0:0] = map(lambda e: (e, depth + 1), entry.directories + entry.files)

