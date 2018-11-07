#!/usr/bin/env python2
#------------------------------------------------------------------
# November 2014, created within ASIG
# Author James Spadaro (jaspadar)
# Co-Author Lilith Wyatt (liwyatt)
#------------------------------------------------------------------
# Copyright (c) 2014-2017 by Cisco Systems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the Cisco Systems, Inc. nor the
#    names of its contributors may be used to endorse or promote products
#    derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#------------------------------------------------------------------
# Class to hold fuzzer data (.fuzzer file info)
# Can read/write .fuzzer files from an instantiation
#------------------------------------------------------------------

from backend.fuzzer_types import MessageCollection, Message
from backend.menu_functions import validateNumberRange
import os.path
import sys

class FuzzerData(object):
    # Init creates fuzzer data and populates with defaults
    # readFromFile to load a .fuzzer file
    def __init__(self):
        # All messages in the conversation
        self.messageCollection = MessageCollection()
        # Directory containing custom processors (Exception, Message, Monitor)
        # or "default"
        self.processorDirectory = "default"
        # Number of times a test case causing a crash should be repeated
        self.failureThreshold = 3
        # How long to wait between retests
        self.failureTimeout = 5
        # Protocol (TCP, UDP)
        self.proto = "tcp"
        # Port to use
        self.port = 0
        # Whether to perform a test run
        self.shouldPerformTestRun = True
        # How long to time out on receive() (seconds)

        # Are we a client or a server? ( default => client )
        self.clientMode = True 
        self.fuzzDirection = Message.Direction.Outbound 
    
        # Which message are we fuzzing? (used for round robin)
        self.currentMessageToFuzz = None
        self.currentSubMessageToFuzz = 0
        
        self.receiveTimeout = 1.0
        # Dictionary to save comments made to a .fuzzer file.  Only really does anything if 
        # using readFromFile and then writeToFile in the same program
        # (For example, fuzzerconverter)
        self.comments = {}
        # Kind of kludgy string for use in readFromFD, made global to not have to pass around
        # Details in readFromFD()
        self._readComments = ""

        # Repurposed for keeping track of which msg we're on if RoundRobin
        # Private: List of messages to be fuzzed
        # Should be set with setFromStr below
        self._messagesToFuzz = []
        # Private: original messages to fuzz str from user input or .fuzzer
        self._messagesToFuzzStr = ""        

        # Private: List of bytes to not fuzz
        # Should be set with setFromStr below
        self._unfuzzedBytes = {}
        # Private: original unfuzzed bytes strings that the above came from
        # (either from user input or .fuzzer file)
        # Example: 1,3,5-10
        self._unfuzzedBytesStrs = {}
    
        # If any message is longer than this, it'll get seperated with 'more' messages
        self.max_cols = 80

        # This designates where the fuzzer information stops and the message processor info
        # begins inside of the .fuzzer file
        self.fuzzer_end_delim = "########END FUZZER########\n" 
        

    # Prevent anyone tampering with the internal unfuzzed bytes storage via properties
    @property
    def unfuzzedBytes(self):
        return self._unfuzzedBytes
    
    # For readability, don't actually implement setter 
    # (Would get confusing if we did unfuzzedBytes = string everywhere)
    @unfuzzedBytes.setter
    def unfuzzedBytes(self, value):
        raise NotImplementedError("NOT SETTING unfuzzedBytes - Use setUnfuzzedBytesFromString")
    
    # Set unfuzzed bytes dict from string (such as "unfuzzedBytes 0 1,3,5-10")
    def setUnfuzzedBytesFromString(self, packetNum, unfuzzedBytesStr):
        self._unfuzzedBytesStrs[packetNum] = unfuzzedBytesStr
        self.unfuzzedBytes[packetNum] = validateNumberRange(unfuzzedBytesStr)
    
    # Edits the submessage and then clears out the rest. 
    def editCurrentlyFuzzedMessage(self,new_message):
        currMsg,currSubmsg = str(float(self.messagesToFuzz[self.currentMessageToFuzz])).split(".") 
        currMsg = int(currMsg)
        currSubmsg = int(currSubmsg)
        self.messageCollection[currMsg].subcomponents[currSubmsg].setOriginalByteArray(new_message)

    # Prevent anyone tampering with the internal messages to fuzz storage via properties
    @property
    def messagesToFuzz(self):
        return self._messagesToFuzz
    
    # For readability, don't implement setter - see above
    @messagesToFuzz.setter
    def messagesToFuzz(self, value):
        raise NotImplementedError("NOT SETTING messagesToFuzz - Use setMessagesToFuzzFromString")
     
    # Set messagesToFuzz from string (such as "1,3-4")
    def setMessagesToFuzzFromString(self, messagesToFuzzStr):
        self._messagesToFuzzStr = messagesToFuzzStr
        self._messagesToFuzz = validateNumberRange(messagesToFuzzStr, flattenList=True)
        #print self._messagesToFuzz

    def addMessagesToFuzz(self,msg_num):
        
        if len(self._messagesToFuzz):
            self._messagesToFuzzStr+=","
         
        self._messagesToFuzzStr+="%s"%msg_num
        #print "msg to fuzz: %s" % self._messagesToFuzzStr
        self.setMessagesToFuzzFromString(self._messagesToFuzzStr)
        
    def getMessagesToFuzzAsString(self):
        return self._messagesToFuzzStr
    
    # Clear messagesToFuzz
    def clearMessagesToFuzz(self):
        self._messagesToFuzz = []
        self._messagesToFuzzStr = ""        

    def rotateNextMessageToFuzz(self):
        try:    
            _ = self._messagesToFuzz[self.currentMessageToFuzz+1] 
            self.currentMessageToFuzz+=1 
            #print "rrotating! new:%d" %(self.currentMessageToFuzz)
        except Exception as e:
            self.currentMessageToFuzz = 0
            #print "rotating! new:%d" %(self.currentMessageToFuzz)
                
            
    # Read in the FuzzerData from the specified .fuzzer file
    def readFromFile(self, filePath, quiet=False):
        with open(filePath, 'r') as inputFile:
            self.readFromFD(inputFile, quiet=quiet)
    
    # Utility function to fix up self.comments and self._readComments within readFromFD()
    # as data is read in
    def _pushComments(self, commentSectionName):
        self.comments[commentSectionName] = self._readComments
        self._readComments = ""

    # Same as above, but appends to existing comment section if possible
    def _appendComments(self, commentSectionName):
        if commentSectionName in self.comments:
            self.comments[commentSectionName] += self._readComments
        else:
            self.comments[commentSectionName] = self._readComments
        self._readComments = ""
    
    # Read in the FuzzerData from a specific file descriptor
    # Most usefully can be used to read from stdout by passing
    # sys.stdin
    def readFromFD(self, fileDescriptor, quiet=False):
        messageNum = 0
        
        # for keeping track we're fuzzing multiple messages (-x round robin)
        messagesToFuzz = []
        # This is used to track multiline messages
        lastMessage = None
        # Build up comments in this string until we're ready to push them out to the dictionary
        # Basically, we build lines and lines of comments, then when a command is encountered,
        # push them into the dictionary using that command as a key
        # Thus, when we go to write them back out, we can print them all before a given key
        self._readComments = ""
        
        for line in fileDescriptor:
            # Record comments on read so we can play them back on write if applicable
            if line.startswith("#") or line == "\n":
                if line == self.fuzzer_end_delim: 
                    #stop processing .fuzzer elements
                    break

                self._readComments += line
                # Skip all further processing for this line
                continue
            
            line = line.replace("\n", "")
            
            # Skip comments and whitespace
            if line.startswith("'''"):
                continue
            if line == "":
                continue
            if line.isspace():
                continue
           
            msg = line.find("'") 
            if msg > -1:
                args = line[:msg].split(" ")
            else:
                args = line.split(" ")

            # Populate FuzzerData obj with any settings we can parse out
            try:
                if args[0] == "processor_dir":
                    self.processorDirectory = args[1]
                    self._pushComments("processor_dir")
                elif args[0] == "failureThreshold":
                    self.failureThreshold = int(args[1])
                    self._pushComments("failureThreshold")
                elif args[0] == "failureTimeout":
                    self.failureTimeout = float(args[1])
                    self._pushComments("failureTimeout")
                elif args[0] == "proto":
                    self.proto = args[1]
                    self._pushComments("proto")
                elif args[0] == "port":
                    self.port = int(args[1])
                    self._pushComments("port")
                elif args[0] == "shouldPerformTestRun":
                    # Use 0 or 1 for setting
                    if args[1] == "0":
                        self.shouldPerformTestRun = False
                    elif args[1] == "1":
                        self.shouldPerformTestRun = True
                    else:
                        raise RuntimeError("shouldPerformTestRun must be 0 or 1")
                    self._pushComments("shouldPerformTestRun")
                elif args[0] == "receiveTimeout":
                    self.receiveTimeout = float(args[1])
                    self._pushComments("receiveTimeout")
                elif args[0] == "messagesToFuzz":
                    print("WARNING: It looks like you're using a legacy .fuzzer file with messagesToFuzz set.  This is now deprecated, so please update to the new format")
                    self.setMessagesToFuzzFromString(args[1])
                    # Slight kludge: store comments above messagesToFuzz with the first message.  *shrug*
                    # Comment saving is best effort anyway, right?
                    self._pushComments("message0")
                elif args[0] == "unfuzzedBytes":
                    print("ERROR: It looks like you're using a legacy .fuzzer file with unfuzzedBytes set.  This has been replaced by the new multi-line format.  Please update your .fuzzer file.")
                    sys.exit(-1)
                # for detecting server or client mode
                elif args[0] == "commsMode":
                    if args[1] == "Server":
                        #print "Fuzzing a client"
                        self.clientMode = False 
                        self.fuzzDirection = Message.Direction.Outbound 
                    elif args[1] == "Client":
                        #print "Fuzzing Server"
                        self.clientMode = True 
                        self.fuzzDirection = Message.Direction.Outbound 

                elif args[0] == "inbound" or args[0] == "outbound":
                    message = Message()
                    message.setFromSerialized(line)
                    self.messageCollection.addMessage(message)
                    if not quiet:
                        print "\tMessage #{0}: {1} bytes {2}".format(messageNum, len(message.getOriginalMessage()), message.direction)
                    self._pushComments("message{0}".format(messageNum))

                    if "fuzz" in args:
                        self.addMessagesToFuzz(messageNum)

                    messageNum += 1
                    subMessageNum = 0
                    lastMessage = message

                    if len(args) > 2:
                        #print args[1:-1]
                        for attr in args[1:-1]:
                            message.attributes.append(attr) 
                            #print message.attributes  
        
                    
                # "more" means this is another line
                elif args[0] == "more":

                    subMessageNum+=1
                    message.appendFromSerialized(line)
                    
                    if "fuzz" in args:
                        self.addMessagesToFuzz("%d.%d"%(messageNum-1,subMessageNum))

                    if not quiet:
                        #print "asfd: %s" % message.subcomponents[-1].message
                        print "\tSubcomponent: {1} additional bytes".format(messageNum, len(line)) 
                    
                    if len(args) > 2:
                        #print args[1:-1]
                        for attr in args[1:-1]:
                            message.subcomponents[-1].attributes.append(attr) 
                            #print message.subcompenents[-1].attributes 

                else:
                    if not quiet:
                        print "Unknown setting in .fuzzer file: {0}".format(args[0])
                # Slap any messages between "message" and "moremessage" (ascii same way) above message
                # It's way too annoying to print these out properly, as they get
                # automagically outserialized by the Message object
                # Plus they may change... eh, forget it, user can fix up themselves if they want
                self._appendComments("message{0}".format(messageNum-1))


                
            except IndexError as e:
                pass
    
            except Exception as e:
                print "Invalid line: {0}".format(line)
                raise e

        # Catch any comments below the last line
        self._pushComments("endcomments")
                        
    # Utility function to get comments for a section after checking if they exist
    # If not, returns ""
    def _getComments(self, commentSectionName):
        if commentSectionName in self.comments:
            return self.comments[commentSectionName]
        else:
            return ""
    
    # Write out the FuzzerData to the specified .fuzzer file
    def writeToFile(self, filePath, defaultComments=False, finalMessageNum=-1):
        origFilePath = filePath
        tail = 0
        while os.path.isfile(filePath):
            tail += 1
            filePath = "{0}-{1}".format(origFilePath, tail)
            # print "File %s already exists" % (filePath,)
        
        if origFilePath != filePath:
            print("File {0} already exists, using {1} instead".format(origFilePath, filePath))

        with open(filePath, 'w') as outputFile:
            self.writeToFD(outputFile, defaultComments=defaultComments, finalMessageNum=finalMessageNum, delim="\\n")
        
        return filePath

    # Write out the FuzzerData to a specific file descriptor
    # if no file descriptor is given, then we just return the buffer
    def writeToFD(self, fileDescriptor=None, defaultComments=False, finalMessageNum=-1, delim=""):
        output_buffer = ""

        # for optional inclusion of processor into .fuzzer
        output_buffer += "'''\n"
        
        if not defaultComments and "start" in self.comments:
            output_buffer += self.comments["start"]
        
        # Processor Directory
        if defaultComments:
            comment = "# Directory containing any custom exception/message/monitor processors\n"
            comment += "# This should be either an absolute path or relative to the .fuzzer file\n"
            comment += "# If set to \"default\", Mutiny will use any processors in the same\n"
            comment += "# folder as the .fuzzer file\n"
            output_buffer += comment
        else:
            output_buffer += self._getComments("processor_dir")
        output_buffer += "processor_dir {0}\n".format(self.processorDirectory)
        
        # Failure Threshold
        if defaultComments:
            output_buffer += "# Number of times to retry a test case causing a crash\n"
        else:
            output_buffer += self._getComments("failure_threshold")
        output_buffer += "failureThreshold {0}\n".format(self.failureThreshold)
        
        # Failure Timeout
        if defaultComments:
            output_buffer += "# How long to wait between retrying test cases causing a crash\n"
        else:
            output_buffer += self._getComments("failureTimeout")
        output_buffer += "failureTimeout {0}\n".format(self.failureTimeout)
        
        # Receive Timeout
        if defaultComments:
            output_buffer += "# How long for recv() to block when waiting on data from server\n"
        else:
            output_buffer += self._getComments("receiveTimeout")
        output_buffer += "receiveTimeout {0}\n".format(self.receiveTimeout)
        
        # Should Perform Test Run
        if defaultComments:
            output_buffer += "# Whether to perform an unfuzzed test run before fuzzing\n"
        else:
            output_buffer += self._getComments("shouldPerformTestRun")
        sPTR = 1 if self.shouldPerformTestRun else 0
        output_buffer += "shouldPerformTestRun {0}\n".format(sPTR)
        
        # Protocol
        if defaultComments:
            output_buffer += "# Protocol (udp or tcp)\n"
        else:
            output_buffer += self._getComments("proto")
        output_buffer += "proto {0}\n".format(self.proto)
        
        # Port
        if defaultComments:
            output_buffer += "# Port number to connect to\n"
        else:
            output_buffer += self._getComments("port")
        output_buffer += "port {0}\n\n".format(self.port)
        
        # commsMode
        output_buffer += "commsMode " 
        output_buffer += "Client\n" if self.clientMode else "Server\n"

        # Messages
        if finalMessageNum == -1:
            finalMessageNum = len(self.messageCollection.messages)-1
        if defaultComments:
            output_buffer += "# The actual messages in the conversation\n# Each contains a message to be sent to or from the server, printably-formatted\n"
            output_buffer += "# Note, if you want to fuzz a submessage (designated by 'more'), then that submessage must also be marked 'fuzz'\n"  

        for i in range(0, finalMessageNum+1):
            
            submsg_count = 0
            message = self.messageCollection[i]
            if not defaultComments:
                output_buffer += self._getComments("message{0}".format(i))

            if ("#msg(%d)\n" % i) not in output_buffer: 
                output_buffer+="#msg(%d)\n" % i

            ascii_count = 0 
            msg_buff = message.getSerialized()
            byte_msg_buff = bytearray(msg_buff[1:-1].decode('string_escape'))
            #print "ORIG_BUF: %s" % msg_buff
            if delim != "":
                for byte in byte_msg_buff:
                    if byte >= 0x20 and byte < 0x7F: 
                        ascii_count+=1
                ascii_percent = float(ascii_count)/len(byte_msg_buff)
            
                if ascii_percent > .80:
                    #! Fix this or make it a command line option to separate as needed. 
                    tmp_buf = message.getSerialized()
                    #print "TEMP_BUF: %s" % tmp_buf
                    delim_loc = tmp_buf.find(delim)+len(delim)

                    if delim_loc > 1:  
                        submsg_count+=1
                        output_buffer += tmp_buf[:delim_loc] + "'\n"
                        tmp_buf = tmp_buf[delim_loc:]
                        delim_loc = tmp_buf.find("\\n")+2
                    else:
                        output_buffer += tmp_buf
                        continue

                    while delim_loc > 1 and delim_loc < len(tmp_buf):
                        #if "#msg(%d.%d)\n" % (i,submsg_count) not in output_buffer: 
                        #    output_buffer+="#msg(%d.%d)\n" % (i,submsg_count)
                        submsg_count+=1
                        output_buffer += "more \'"
                        output_buffer += tmp_buf[:delim_loc] + "'\n"
                        tmp_buf = tmp_buf[delim_loc:]
                        delim_loc = tmp_buf.find(delim)+2

                    output_buffer = output_buffer.replace("more ''\n","")

                    if len(tmp_buf) > 2:
                        if "#msg(%d.%d)\n" % (i,submsg_count) not in output_buffer: 
                            output_buffer+="#msg(%d.%d)\n" % (i,submsg_count)
                        submsg_count+=1
                        output_buffer+="more \'%s" % tmp_buf
                else: # small ascii percent :(
                    output_buffer += msg_buff
            else:
                output_buffer += msg_buff


        if not defaultComments:
            output_buffer += self._getComments("endcomments")
    

        # closing terminator for processing as python
        output_buffer+="'''\n"
        output_buffer+="%s" % self.fuzzer_end_delim

        # read in our message proc template into the output_buffer
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),"message_proc_base.py")) as f:
            output_buffer += f.read() 


        if fileDescriptor:
            fileDescriptor.write(output_buffer)
        else:
            return output_buffer
        
