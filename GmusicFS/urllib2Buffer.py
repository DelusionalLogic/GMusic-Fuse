import urllib2

class ResponseBuffer(object):
    '''Buffer addon for urllib2 response'''

    def __init__(self, response, length=-1):
        self.__response = response
        if "Content-Length" in response.headers:
            self.__length = response.headers['Content-Length']
        else:
            if length == -1:
                raise Exception("No length was given and no Content-Length header was found")
            self.__length = length
        self.__position = 0
        self.__curlength = 0
        self.__buffer = ""
        self.__closed = False

    def read(self, numbytes):
        if self.__closed:
            raise BufferError("Buffer closed")

        readbytes = (self.__position + numbytes) - self.__curlength
        if readbytes > 0:
            print "Reading new data to buffer"
            newdata = self.__response.read(readbytes)
            self.__buffer += newdata
            self.__curlength += readbytes
        data = self.__buffer[self.__position: self.__position + numbytes]
        self.seek(numbytes)
        return data

    def seek(self, numbytes, offpos=0):
        if self.__closed:
            raise BufferError("Buffer closed")

        if offpos == 0:
            self.__position = numbytes
        elif offpos == 1:
            self.__position += numbytes
        else:
            self.__position = self.__length - numbytes
        if self.__position >= self.__length or self.__position < 0:
            raise BufferError("Tried to seek out of buffer")

    def close(self):
        self.__response.close()
