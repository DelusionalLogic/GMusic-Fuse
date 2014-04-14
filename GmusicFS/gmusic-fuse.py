#pylint: disable=R0904
from sys import argv
from stat import S_IFDIR, S_IFREG
import collections
import urllib2
import random
import ConfigParser
import argparse
from struct import pack

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

from gmusicapi import Mobileclient

from urllib2Buffer import ResponseBuffer

def splitPath(path):
    return path.strip('/').split('/')

def sanitizename(name):
    for char in r'\/:*?"<>|':
        name = name.replace(char, '')
    return name

def normalize(name):
    return sanitizename(name.strip().lower())

def cleanname(name):
    name = sanitizename(name)
    return name

SongHandle = collections.namedtuple("SongHandle", ['buffer', 'count'])
ApiInfo = collections.namedtuple("ApiInfo", ['api', 'deviceid'])


def getbuffer(apiinfo, songid, length):
    url = apiinfo.api.get_stream_url(songid, apiinfo.deviceid)
    response = urllib2.urlopen(url)
    return ResponseBuffer(response, length)

class Song(object):
    '''Song object'''

    def __init__(self, apiinfo, name, uid, duration, size):
        self.__apiinfo = apiinfo
        self.name = name
        self.uid = uid
        self.duration = duration
        self.size = size

    def getbuffer(self):
        return getbuffer(self.__apiinfo, self.uid, self.size)

class Album(object):
    '''Album Object'''

    def __init__(self, apiinfo, name, uid, cover):
        self.__apiinfo = apiinfo
        self.name = name
        self.uid = uid
        self.cover = cover
        self.__songs = {}

    def addsong(self, song):
        key = normalize(song.name)
        self.__songs[key] = song

    def getsong(self, name):
        if not name in self.__songs:
            raise ValueError("No song of that name")
        return self.__songs[name]

    def hassong(self, name):
        return name in self.__songs

    def getsongs(self):
        return self.__songs

class Artist(object):
    '''Artist container'''

    def __init__(self, apiinfo, name, uid):
        self.__apiinfo = apiinfo
        self.name = name
        self.uid = uid
        self.__albums = {}

    def addalbum(self, album):
        key = normalize(album.name)
        self.__albums[key] = album

    def getalbum(self, name):
        if not name in self.__albums:
            raise ValueError("No album of that name")
        return self.__albums[name]

    def getalbums(self):
        return self.__albums

    def hasalbum(self, name):
        return name in self.__albums

class GMusicClient(object):
    '''
    A client to conver the gmusicapi dicts to native types
    '''

    def __init__(self, username, password, deviceid):
        self.__apiinfo = ApiInfo(Mobileclient(), deviceid)
        if not self.__apiinfo.api.login(username, password):
            raise Exception("Google music login failed")
        self.__dirty = True
        self.__artists = {}

    def __updateinfo(self):
        songdict = self.__apiinfo.api.get_all_songs()
        for song in songdict:
            if song["artist"] == "" or song["album"] == "":
                continue

            key = normalize(song["artist"])
            if key in self.__artists:
                artist = self.__artists[key]
            else:
                if "artistId" in song:
                    uid = song["artistId"]
                else:
                    uid = "UNKNOWN"
                artist = Artist(self.__apiinfo, song["artist"], uid)
                self.__artists[key] = artist

            key = normalize(song["album"])
            if artist.hasalbum(key):
                album = artist.getalbum(key)
            else:
                if "albumId" in song:
                    uid = song["albumId"]
                else:
                    uid = "UNKNOWN"
                album = Album(self.__apiinfo, song["album"], uid, "example.com")
                artist.addalbum(album)

            song = Song(self.__apiinfo, song["title"], song["id"], int(song["durationMillis"]), int(song["estimatedSize"]))
            album.addsong(song)
        self.__dirty = False

    def getartists(self):
        if self.__dirty:
            self.__updateinfo()
        return self.__artists

    def getartist(self, name):
        if self.__dirty:
            self.__updateinfo()
        if not name in self.__artists:
            raise ValueError("No artist of that name")
        return self.__artists[name]

class Provider(object):
    #pylint: disable=R0201
    '''
    A base provider class
    '''

    def getartists(self):
        raise Exception("Not Implemented")

    def getalbums(self, artist):
        raise Exception("Not Implemented")

    def getsongs(self, artist, album):
        raise Exception("Not Implemented")

class GMusicProvider(Provider):
    '''
    A Gmusic Provider
    '''

    def __init__(self, username, password, deviceid):
        self.__client = GMusicClient(username, password, deviceid)
        self.openfiles = {}

    def getartist(self, artist):
        return self.__client.getartist(artist)

    def opensong(self, artist, album, name, fh):
        if fh in self.openfiles:
            print "Open file: " + name + "Opened again"
            try:
                self.openfiles[fh].count += 1
                return
            except AttributeError:
                pass
        song = self.__client.getartist(artist).getalbum(album).getsong(name)
        self.openfiles[fh] = SongHandle(song.getbuffer(), 1)

    def closesong(self, fh):
        if not fh in self.openfiles:
            raise Exception("Unexpected file close")
        if self.openfiles[fh].count <= 1:
            self.openfiles[fh].buffer.close()
            del self.openfiles[fh]
        else:
            self.openfiles[fh].count -= 1

    def getsongbytes(self, fh, size, offset, artist, album, title):
        if not fh in self.openfiles:
            raise Exception("Unexpected file read")
        handle = self.openfiles[fh].buffer
        handle.seek(offset)
        buf = handle.read(size)
        return buf

    def getartists(self):
        artistnames = [cleanname(name) for name in self.__client.getartists()]
        print(artistnames)
        return artistnames

    def getalbums(self, artist):
        albums = self.__client.getartist(artist).getalbums()
        albumnames = [cleanname(name) for name in albums]
        return albumnames

    def getsongs(self, artist, album):
        songs = self.__client.getartist(artist).getalbum(album).getsongs()
        songnames = [cleanname(name) for name in songs]
        return songnames

class GMusic(LoggingMixIn, Operations):
    '''
    A Gmusic Filesystem
    '''

    def __init__(self, musicProvider):
        self.__musicprovider = musicProvider

    def getattr(self, path, fh=None):
        st = {
            'st_mode' : (S_IFDIR | 0755),
            'st_nlink' : 2
        }

        parts = splitPath(path)
        if parts[0] == "artists" and len(parts) == 4:
            artist = self.__musicprovider.getartist(parts[1])
            album = artist.getalbum(parts[2])
            song = album.getsong(parts[3])
            st = {
                'st_mode' : (S_IFREG | 0444),
                'st_size' : song.size,
                'st_ctime' : 0,
                'st_mtime' : 0,
                'st_atime' : 0
            }
        return st

    def open(self, path, fh):
        fh = random.getrandbits(64)
        parts = splitPath(path)
        if parts[0] == "artists" and len(parts) == 4:
            self.__musicprovider.opensong(parts[1], parts[2], parts[3], fh)
        return fh

    def release(self, path, fh):
        self.__musicprovider.closesong(fh)

    def read(self, path, size, offset, fh):
        parts = splitPath(path)
        if parts[0] == "artists" and len(parts) == 4:
            return self.__musicprovider.getsongbytes(fh, size, offset, parts[1], parts[2], parts[3])

    def readdir(self, path, fh):
        parts = splitPath(path)
        contents = []
        print parts
        if parts[0] == "":
            contents.append("artists")
        elif parts[0] == "artists":
            if len(parts) == 1:
                contents.extend(self.__musicprovider.getartists())
            elif len(parts) == 2:
                contents.extend(self.__musicprovider.getalbums(parts[1]))
            elif len(parts) == 3:
                contents.extend(self.__musicprovider.getsongs(parts[1], parts[2]))
        return ['.', '..'] + contents

def main():
    parser = argparse.ArgumentParser(description="Fuse fs for accessing Google Music")
    parser.add_argument("mountpoint", help="The location to mount to")
    parser.add_argument('-f', '--foreground', dest='foreground', 
                        action="store_true",
                        help='Run in the foreground.')
    args = parser.parse_args()

    config = ConfigParser.ConfigParser()
    config.read("cred.conf")
    username = config.get('credentials', 'username')
    password = config.get('credentials', 'password')
    deviceid = config.get('device', 'deviceid')
    fuse = FUSE(GMusic(GMusicProvider(username, password, deviceid)), args.mountpoint,
                    foreground=args.foreground, 
                    ro=True, nothreads=True)

if __name__ == '__main__':
    main()
