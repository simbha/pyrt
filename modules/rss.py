#!/usr/bin/env python

""" Copyright (C) 2012 mountainpenguin (pinguino.de.montana@googlemail.com)
    <http://github.com/mountainpenguin/pyrt>
    
    This file is part of pyRT.

    pyRT is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    pyRT is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with pyRT.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import print_function
import logging
import sys
import signal
import time
import multiprocessing
import os
import hashlib
import re
import traceback

from modules import websocket
from modules import rpc
from modules import feedparser
#from modules import posthandler
        
class RSS(object):
    def __init__(self, l, log, s, websocketURI=".sockets/rss.interface"):
        self.LOGIN = l
        self.LOG = log
        self.STORE = s
        self.websocketURI = websocketURI
        self.authkey = self.LOGIN.getRPCAuth()
        
    def shutdownRSS(self, *args, **kwargs):
        logging.info("RSS exiting")
        sys.exit(0)
        
    def processFeed(self, feed):
        try:
            f = feedparser.parse(feed["url"])
        except:
            self.RPC.RPCCommand("log","error","Invalid RSS feed (id: %s, alias: %s), disabling", feed["id"], feed["alias"])
            self.RPC.RPCCommand("disable_rss", feed["id"])
        else:
            if len(f.entries) == 0:
                self.RPC.RPCCommand("log","warning", "RSS feed (id: %s, alias: %s) is empty", feed["id"], feed["alias"])
                return
            
            lasthash = hashlib.sha256(f.entries[0].link).hexdigest()
            if lasthash == feed["lasthash"]:
                #no new entries
                #self.RPC.RPCCommand("log", "debug", "No new entries for feed (id: %s, alias: %s)", feed["id"], feed["alias"])
                pass
            else:
                self.RPC.RPCCommand("updatehash_rss", feed["id"], lasthash)
                newentries = [f.entries[0]]
                for e in f.entries[1:]:
                    h = hashlib.sha256(e.link).hexdigest()
                    if h == feed["lasthash"]:
                        break
                    else:
                        newentries.append(e)
                #self.RPC.RPCCommand("log","debug","%i new entries for feed (id: %s, alias: %s)", len(newentries), feed["id"], feed["alias"])
                for e in newentries:
                    for positive, negative, sizelim in feed["filters"]:
                        contTrue = 0
                        for regex in [re.compile(x, re.I) for x in positive]:
                            if not regex.search(e.title):
                                break
                            else:
                                contTrue += 1
                        if contTrue != len(positive):
                            continue
                        
                        cont = True

                        for regex in [re.compile(y, re.I) for y in negative]:
                            if regex.search(e.title):
                                cont = False
                                break
                            else:
                                cont = True
                                
                        if not cont:
                            continue

                        self.RPC.RPCCommand("fetch_torrent_rss", ID=feed["id"], alias=feed["alias"], link=e.link, sizelim=sizelim)
        
    def refreshRSS(self):
        feeds_req = self.RPC.RPCCommand("get_active_rss")
        if not feeds_req or feeds_req.response == "True":
            return
        
        if feeds_req.error:
            self.RPC.RPCCommand("log", "error", "Error in RSS process: %s", feeds_req.error)
            return
        
        timestamp = time.time()
        if not feeds_req.response:
            return
        
        for feed in feeds_req.response:
            timediff = timestamp - feed["updated"]
            if timediff > feed["ttl_sec"]:
                args = [feed["id"], timestamp]
                self.RPC.RPCCommand("update_rss", *args)
                self.processFeed(feed)
        
    def startRSS(self):
        sock = websocket.create_connection(self.websocketURI)
        self.RPC = rpc.RPC(self.authkey, "RSS", sock)
        signal.signal(signal.SIGTERM, self.shutdownRSS)
        self.RPC.RPCCommand("log","info", "RSS started in the background")
        while True:
            try:
                self.refreshRSS()
            except:
                tb = traceback.format_exc()
                self.RPC.RPCCommand("publicLog", "error", "ERROR in RSS process: %s", tb.strip().split("\n")[-1])
                self.RPC.RPCCommand("privateLog", "error", "ERROR in RSS process:\n%s", tb)
            time.sleep(10)
    
    def start(self):
        p = multiprocessing.Process(target=self.startRSS)
        p.daemon = True
        p.start()
        return p.pid
