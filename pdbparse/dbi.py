#!/usr/bin/env python

from construct import *

_ALIGN = 4

_DEBUG = False

def get_parsed_size(tp,con):
    return len(tp.build(con))

def SymbolRange(name):
    return Struct(name,
        SLInt16("section"),
        Padding(2),
        SLInt32("offset"),
        SLInt32("size"),
        ULInt32("flags"),
        SLInt16("module"),
        Padding(2),
        ULInt32("dataCRC"),
        ULInt32("relocCRC"),
    )

DBIHeader = Struct("DBIHeader",
    Const(Bytes("magic", 4), "\xFF\xFF\xFF\xFF"),                           # 0
    ULInt32("version"),                                                     # 4
    ULInt32("age"),                                                         # 8
    SLInt16("gssymStream"),                                                 # 12
    ULInt16("vers"),                                                        # 14
    SLInt16("pssymStream"),                                                 # 16
    ULInt16("pdbver"),                                                      # 18
    SLInt16("symrecStream"),           # stream containing global symbols   # 20
    ULInt16("pdbver2"),                                                     # 22
    ULInt32("module_size"),         # total size of DBIExHeaders            # 24
    ULInt32("secconSize"),                                                  # 28
    ULInt32("secmapSize"),                                                  # 32
    ULInt32("filinfSize"),                                                  # 36
    ULInt32("tsmapSize"),                                                   # 40
    ULInt32("mfcIndex"),                                                    # 44
    ULInt32("dbghdrSize"),                                                  # 48
    ULInt32("ecinfoSize"),                                                  # 52
    ULInt16("flags"),                                                       # 56
    Enum(ULInt16("Machine"),                                                # 58
        IMAGE_FILE_MACHINE_UNKNOWN = 0x0,
        IMAGE_FILE_MACHINE_I386 = 0x014c,
        IMAGE_FILE_MACHINE_IA64 = 0x0200,
        IMAGE_FILE_MACHINE_AMD64 = 0x8664,
    ),
    ULInt32("resvd"),                                                       # 60
)

DBIExHeader = Struct("DBIExHeader",
    ULInt32("opened"),
    SymbolRange("range"),
    ULInt16("flags"),
    SLInt16("stream"),
    ULInt32("symSize"),
    ULInt32("oldLineSize"),
    ULInt32("lineSize"),
    SLInt16("nSrcFiles"),
    Padding(2),
    ULInt32("offsets"),
    ULInt32("niSource"),
    ULInt32("niCompiler"),
    CString("modName"),
    CString("objName"),
)

DbiDbgHeader = Struct("DbiDbgHeader",
    SLInt16("snFPO"),
    SLInt16("snException"),
    SLInt16("snFixup"),
    SLInt16("snOmapToSrc"),
    SLInt16("snOmapFromSrc"),
    SLInt16("snSectionHdr"),
    SLInt16("snTokenRidMap"),
    SLInt16("snXdata"),
    SLInt16("snPdata"),
    SLInt16("snNewFPO"),
    SLInt16("snSectionHdrOrig"),
)

sstFileIndex = Struct("sstFileIndex",
    ULInt16("cMod"),
    ULInt16("cRef"),
)

def parse_stream(stream):
    pos = 0
    dbihdr = DBIHeader.parse_stream(stream)
    pos += get_parsed_size(DBIHeader, dbihdr)
    stream.seek(pos)
    dbiexhdr_data = stream.read(dbihdr.module_size)

    # sizeof() is broken on CStrings for construct, so
    # this ugly ugly hack is necessary
    dbiexhdrs = []
    while dbiexhdr_data:
        dbiexhdrs.append(DBIExHeader.parse(dbiexhdr_data))
        sz = get_parsed_size(DBIExHeader,dbiexhdrs[-1])
        if sz % _ALIGN != 0: sz = sz + (_ALIGN - (sz % _ALIGN))
        dbiexhdr_data = dbiexhdr_data[sz:]

    # "Section Contribution"
    stream.seek(dbihdr.secconSize, 1)
    # "Section Map"
    stream.seek(dbihdr.secmapSize, 1)
    #
    # see: http://pierrelib.pagesperso-orange.fr/exec_formats/MS_Symbol_Type_v1.0.pdf
    # the contents of the filinfSize section is a 'sstFileIndex'
    #
    # "File Info"
    end = stream.tell() + dbihdr.filinfSize
    fileIndex = sstFileIndex.parse_stream(stream)
    modStart = Array(fileIndex.cMod, ULInt16("modStart")).parse_stream(stream)
    cRefCnt = Array(fileIndex.cMod, ULInt16("cRefCnt")).parse_stream(stream)
    NameRef = Array(fileIndex.cRef, ULInt32("NameRef")).parse_stream(stream)
    modules = [] # array of arrays of files
    files = [] # array of files (non unique)
    Names = stream.read(end - stream.tell())

    if _DEBUG:
        print 'len(Names): ', len(Names) # 3013624
        print 'len(Names)/4: ', len(Names)/4
        print 'len(NameRef): ', len(NameRef) # 160
        print 'fileIndex.cMod (i): ', fileIndex.cMod # 2282
        print 'len(modStart): ', len(modStart) # 2282
        print 'len(cRefCnt): ', len(cRefCnt) # 2282

    skipped_names = 0
    lenNameRef = len(NameRef)
    for i in xrange(0, fileIndex.cMod):
        these = []
        for j in xrange(modStart[i], modStart[i] + cRefCnt[i]):
            if j >= lenNameRef:
                if _DEBUG:
                    print "IPL: Warning - out of bound access to NameRef, index {}, NameRef length: {}".format(j, lenNameRef)
                    print "IPL: ... modStart[i] = {}, cRefCnt[i] = {}".format(modStart[i], cRefCnt[i])
                skipped_names += 1
                if skipped_names > 10:
                    break
                continue
            Name = CString("Name").parse(Names[NameRef[j]:])
            files.append(Name)
            these.append(Name)
        modules.append(these)

    if _DEBUG:
        print "IPL: {} skipped names".format(skipped_names)

    #stream.seek(dbihdr.filinfSize, 1)
    # "TSM"
    stream.seek(dbihdr.tsmapSize, 1)
    # "EC"
    stream.seek(dbihdr.ecinfoSize, 1)
    # The data we really want
    dbghdr = DbiDbgHeader.parse_stream(stream)

    return Container(DBIHeader=dbihdr,
                     DBIExHeaders=ListContainer(dbiexhdrs),
                     DBIDbgHeader=dbghdr,
                     modules=modules,
                     files=files)

def parse(data):
    return parse_stream(StringIO(data))
