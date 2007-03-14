#
# Copyright (c) 2005,2006,2007 Jonathan Harris
# 
# Mail: <x-plane@marginal.org.uk>
# Web:  http://marginal.org.uk/x-planescenery/
#
# See FS2XPlane.html for usage.
#
# This software is licensed under a Creative Commons License
#   Attribution-ShareAlike 2.5:
#
#   You are free:
#     * to copy, distribute, display, and perform the work
#     * to make derivative works
#     * to make commercial use of the work
#   Under the following conditions:
#     * Attribution: You must give the original author credit.
#     * Share Alike: If you alter, transform, or build upon this work, you
#       may distribute the resulting work only under a license identical to
#       this one.
#   For any reuse or distribution, you must make clear to others the license
#   terms of this work.
#
# This is a human-readable summary of the Legal Code (the full license):
#   http://creativecommons.org/licenses/by-sa/2.5/legalcode
#

from glob import glob
from math import acos, atan, atan2, cos, fmod, floor, pow, sin, pi, radians, degrees
from os import listdir
from os.path import basename, dirname, exists, join, normpath, pardir, splitext
import struct
from struct import unpack
from sys import maxint
import types

from convutil import cirp, m2f, NM2m, complexity, asciify, unicodeify, normalize, rgb2uv, cross, dot, AptNav, Object, Polygon, Point, Matrix, apronlightspacing, taxilightspacing, FS2XError, unique
from convobjs import maketaxilight, makegenquad, makegenmulti
from convtaxi import taxilayout, Node, Link

# Subset of XML TaxiwayPoint
class TaxiwayPoint:
    def __init__(self, loc):
        self.type='NORMAL'
        self.lat=loc.lat
        self.lon=loc.lon

# Subset of XML TaxiwayPath
class TaxiwayPath:
    # width<0 -> no lights. -1<=width<=1 -> no draw & no edge
    def __init__(self, type, width, centerline, start, end):
        self.type=type	# TAXI or VEHICLE
        if width>0:
            self.width=width
        else:
            self.width=-width
        self.surface='ASPHALT'
        if self.width>1:
            self.drawSurface=self.drawDetail='TRUE'
            if type=='VEHICLE':
                self.centerLine=centerline
                if centerline and width>0:
                    self.centerLineLighted='TRUE'
                else:
                    self.centerLineLighted='FALSE'
                self.rightEdge=self.leftEdge='SOLID'
                self.rightEdgeLighted=self.leftEdgeLighted='FALSE'
            else:
                self.centerline=self.centerLineLighted='FALSE'
                self.rightEdge=self.leftEdge='NONE'
                if width>0:
                    self.rightEdgeLighted=self.leftEdgeLighted='TRUE'
                else:
                    self.rightEdgeLighted=self.leftEdgeLighted='FALSE'
        else:
            self.drawSurface=self.drawDetail='FALSE'
            self.centerline=self.centerLineLighted='FALSE'
            self.rightEdge=self.leftEdge='NONE'
            self.rightEdgeLighted=self.leftEdgeLighted='FALSE'
        self.start=start
        self.end=end
        self.name=0

# Subset of XML TaxiwayName
class TaxiwayName:
    def __init__(self, name):
        self.name=name
        
                 
# Read BGL header
class Parse:
    def __init__(self, bgl, srcfile, output):
        if output.debug:
            debug=file(join(output.xppath,'debug.txt'),'at')
            debug.write('%s\n' % srcfile)
        else:
            debug=None
        # Per-BGL counts
        output.gencount=0
        output.anccount=0	# Not used for library objects
        name=basename(srcfile)
        for section in [42,54,58,102,114]:
            bgl.seek(section)
            (secbase,)=unpack('<I',bgl.read(4))
            if (secbase):
                bgl.seek(secbase)
                if section==42:
                    output.log('Skipping traffic data in file %s' % name)
                elif section==54:
                    try:
                        ProcTerrain(bgl, srcfile, output, debug)
                    except:
                        output.log("Can't parse Terrain section in file %s" % name)
                elif section==58:
                    # OBJECT
                    areano=0
                    old=False
                    rrt=False
                    anim=False
                    while True:
                        # LatBand
                        posl=bgl.tell()
                        (c,)=unpack('<B', bgl.read(1))
                        if not c in [0, 21]:
                            if debug: debug.write("!Bogus LatBand %2x\n" % c)
                            raise struct.error	# wtf?
                        if c==0:
                            break
                        (foo,off)=unpack('<Ii', bgl.read(8))
                        bgl.seek(secbase+off)
                        while True:
                            # Header
                            areano+=1                        
                            posa=bgl.tell()
                            if debug: debug.write("----\nArea %x\n" % posa)
                            (c,)=unpack('<B', bgl.read(1))
                            bgl.read(9)
                            if c==0:
                                break
                            elif c in [6,9,12,14]:
                                (l,)=unpack('<I',bgl.read(4))
                            elif c in [5,8,11,13]:
                                (l,)=unpack('<H',bgl.read(2))
                            elif c in [4,7,10]:
                                (l,)=unpack('<B',bgl.read(1))
                            else:
                                if debug:debug.write("!Bogus area type %x\n"%c)
                                raise struct.error	# wtf?
                            try:
                                p=ProcScen(bgl, posa+l, 1.0, None, srcfile,
                                           output, None, None, debug)
                                if p.old:
                                    old=True
                                    if debug: debug.write("Pre-FS2002\n")
                                if p.rrt:
                                    rrt=True
                                    if debug: debug.write("Old-style rr\n")
                                if p.anim:
                                    anim=True
                                    if debug: debug.write("Animation\n")
                            except:
                                output.log("Can't parse area #%d in %s" % (
                                    areano, name))
                                if debug: debug.write("!Can't parse area %x\n" % posa)
                            bgl.seek(posa+l)
                        bgl.seek(posl+9)
                    if anim:
                        output.log("Skipping animation in file %s" % name)
                    if old:
                        output.log("Skipping pre-FS2002 scenery in file %s" % name)
                    if rrt:
                        output.log("Skipping pre-FS2004 runways and/or roads in file %s" % name)
                elif section==102:
                    # Miscellaneous
                    while True:
                        # LatBand
                        posl=bgl.tell()
                        (c,)=unpack('<B', bgl.read(1))
                        if not c in [0, 21]:
                            if debug: debug.write("!Bogus LatBand %2x\n" % c)
                            raise struct.error	# wtf?
                        if c==0:
                            break
                        (foo,off)=unpack('<Ii', bgl.read(8))
                        bgl.seek(secbase+off)
                        try:
                            ProcMisc(bgl, srcfile, output, debug)
                        except:
                            output.log("Can't parse Miscellaneous section in file %s" % name)
                        bgl.seek(posl+9)
        if debug: debug.close()


# handle section 9 area and 10 library. libname!=None if this is a library
class ProcScen:
    def __init__(self, bgl, enda, scale, libname, srcfile, output,
                 scen, tran, debug):

        self.old=False	# Old style scenery found and skipped
        self.rrt=False	# Old style runways/roads found and skipped
        self.anim=False	# Animations found and skipped
        self.debug=debug

        self.bgl=bgl
        self.libname=libname
        self.srcfile=basename(srcfile)
        if libname:
            self.comment="object %s in file %s" % (
                libname,asciify(self.srcfile))
        else:
            self.comment="file %s" % asciify(self.srcfile)	# Used for reporting
        self.output=output
        self.texdir=normpath(join(dirname(srcfile), pardir))
        # For case-sensitive filesystems
        for d in listdir(self.texdir):
            if d.lower()=='texture':
                self.texdir=join(self.texdir, d)
                break
        else:
            raise FS2XError('"%s" does not exist' %join(self.texdir,'Texture'))

        start=bgl.tell()
        if tran: self.tran=start+tran		# Location of TRAN table
        if scen:
            # Decode SCEN table
            bgl.seek(start+scen)
            (count,)=unpack('<H', bgl.read(2))
            scen=start+scen+2
            self.scen=[None for i in range(count)]
            for i in range(count):
                bgl.seek(scen+i*12)
                (out,child,peer,size,offset)=unpack('<hhhhi', bgl.read(12))
                # Child and Peer are offsets; convert to scene nos
                if child!=-1:
                    bgl.seek(scen+child*12)
                    (child,)=unpack('<h',bgl.read(2))
                if peer!=-1:
                    bgl.seek(scen+peer*12)
                    (peer,)=unpack('<h',bgl.read(2))
                # Convert offsets to file positions
                self.scen[out]=(child, peer, size, scen+i*12+offset, -1)
            # Invert Child/Peer pointers to get parents
            for i in range(count):
                (child, peer, size, posa, parent)=self.scen[i]
                if child!=-1:	# child's parent is me
                    (xchild, xpeer, xsize, xposa, xparent)=self.scen[child]
                    self.scen[child]=(xchild, xpeer, xsize, xposa, i)
                if peer!=-1:	# peer's parent is my parent
                    (xchild, xpeer, xsize, xposa, xparent)=self.scen[peer]
                    self.scen[peer]=(xchild, xpeer, xsize, xposa, parent)
            if self.debug:
                # Dump SCEN table
                self.debug.write("SCEN: %-2d        ANIC\n" % count)
                maxt=-1
                for i in range(count):
                    (child,peer,size,posa,parent)=self.scen[i]
                    bgl.seek(posa)
                    (cmd,src,dst)=unpack('<3H', bgl.read(6))
                    c="%2d: %2d %2d %2d -> %2x " %(i, child, peer, parent, cmd)
                    if cmd==0xc6 and size==6:
                        c+="%2d %2d\n" % (src, dst)
                        maxt=max(maxt,src)
                    else:
                        c+="size=%d\n" % size
                    self.debug.write(c)
                # Dump TRAN table
                count=maxt+1
                self.debug.write("TRAN: %d\n" % count)
                bgl.seek(self.tran)
                for i in range(count):
                    m=[]
                    for j in range(4):
                        (a,b,c,d)=unpack('<4f', bgl.read(16))
                        m.append([a,b,c,d])
                    self.debug.write("%s = %d\n" % (Matrix(m), i))
            bgl.seek(start)
        
        # State
        self.complexity=1
        self.loc=None
        self.alt=0
        self.altmsl=0
        self.layer=None
        self.matrix=[None]
        self.scale=scale
        self.basescale=scale
        self.stack=[]	# (return address, layer, pop matrix?)
        self.tex=[]
        self.mat=[[(0.5,0.5,0.5),(0,0,0),(0,0,0)]]	# [[a,s,e]]
        self.vtx=[]
        self.idx=[]	# Indices into vtx
        self.m=None	# Index into mat
        self.t=-1	# Index into tex
        self.billboard=None	# Emulating billboarding in a libary defn

        self.nodes=[]
        self.links=[]
        self.linktype=None	# Last road/river/taxiway (type, width, centerline)
        self.pnt=None	# Last line location (x,y,z)
        self.haze=0	# Whether palette-based transaprency. 0=none
        self.concave=False
        
        self.objdat={}	# (mat, vtx[], idx[]) by (loc, layer, alt, altmsl, matrix, scale, tex, lit)
        self.linedat={}	# (vtx[], idx[], (r,g,b)) by (loc, layer, alt, altmsl, matrix, scale, None, None)
        self.lightdat={}# ((x,y,z), (r,g,b)) by (loc, layer, alt, altmsl, matrix, scale, None, None)
        self.polydat=[]	# ((points, layer, heading, scale, tex, lit))

        self.neednight=False
        self.dayobjdat={}        
        self.daylinedat={}        
        self.daylightdat={}        
        self.daypolydat=[]

        self.vars={
            # Vars not listed are assumed to be 0
            0: 0,	# dummy
            #0x07e: 0,	# FS5_CG_TO_GROUND_X: ???
            0x280: 0,	# altmsl (presumably of airplane?)
            0x282: 1,	# beacon: rotating bitmap shifted 1 bit/3 sec
            0x28c: 1,	# tod: 2|4 indicates night?
            0x30A: 6,	# beacon_2: 16-bit bitmap with 0x0506 add/3 sec
            0x30C: 8,	# beacon_3: 16-bit bitmap with 0x0708 add/3 sec 
            0x30E: 0xa,	# beacon_4: 16-bit bitmap with 0x090A add/3 sec 
            0x310: 0xc,	# beacon_5: 16-bit bitmap with 0x0B0C add/3 sec
            #0x312-31a	# usrvar-usrvar5
            #0x338, 1,	# SHADOW_FLAG: 0=do crash detection???
            0x33a: 0,	# rbias: eye to object distance in meters II.FF
            0x33b: 0,	# rbias_1: eye to object distance in meters IIII
            0x340: 255,	# ground_texture
            0x342: 255,	# building_texture
            0x344: 255,	# aircraft_texture
            0x346: 5,	# image_complex: complexity of the scenery 0-5
            0x37e: 0,	# xv: rotated X-axis eye to object distance
            0x382: 0,	# yv: rotated Y-axis eye to object distance
            0x386: 0,	# zv: rotated Z-axis eye to object distance
            0x389: 12,	# zulu hours in the day - Midday
            0x390: 0,	# water_texture
            0xc72: 5,	# ground wind velocity [kts?]
            0xc74: 0,	# ground wind direction [units?]
            0xc76: 0,	# ground wind turbulence [units?]
            }
        self.setseason()

        cmds={0x02:self.NOP,
              0x05:self.NOP,
              0x06:self.SPnt,
              0x07:self.CPnt,
              0x08:self.Closure,
              0x0d:self.Jump,
              0x0f:self.StrRes,
              0x10:self.StrRes,    
              0x14:self.SColor,
              0x17:self.TextureEnable,
              0x18:self.Texture,
              0x1a:self.ResList,
              0x1b:self.Jump,
              0x1c:self.IfIn2,
              0x1e:self.Haze,
              0x1f:self.TaxiMarkings,
              0x20:self.FaceTTMap,
              0x21:self.IfIn3,
              0x22:self.Return,
              0x23:self.Call,
              0x24:self.IfIn1,
              0x25:self.SeparationPlane,
              0x26:self.SetWrd,
              0x29:self.GResList,
              0x30:self.NOPh,
              0x2a:self.FaceT,
              0x2b:self.Call32,
              0x2d:self.SColor24,
              0x2e:self.SColor24,
              0x2f:self.Scale,
              0x32:self.Call,
              0x33:self.Instance,
              0x34:self.SuperScale,
              0x35:self.PntRow,
              0x37:self.Point,
              0x38:self.Concave,
              0x39:self.IfMsk,
              0x3b:self.VInstance,
              0x3c:self.Position,
              0x3e:self.FaceT,
              0x42:self.TextureRunway,
              0x43:self.Texture2,
              0x44:self.TextureRunway,
              0x4d:self.MoveL2G,
              0x4e:self.MoveL2G,
              0x46:self.PointVICall,
              0x49:self.Building,
              0x3f:self.NOPh,
              0x50:self.SColor,
              0x51:self.SColor,
              0x52:self.SColor,
              0x55:self.SurfaceType,
              0x5d:self.TextureRepeat,
              0x5f:self.IfSizeV,
              0x62:self.IfVis,
              0x63:self.LibraryCall,
              0x69:self.RoadStart,
              0x6a:self.RoadCont,
              0x6b:self.RiverStart,
              0x6c:self.RiverCont,
              0x6d:self.IfSizeV,
              0x6e:self.TaxiwayStart,
              0x6f:self.RoadCont,
              0x76:self.NOP,
              0x73:self.Jump,
              0x74:self.AddCat,
              0x77:self.ScaleAGL,
              0x7a:self.FaceTTMap,
              0x7d:self.NOP,
              0x80:self.ResPnt,
              0x81:self.NOPh,
              0x83:self.ReScale,
              0x88:self.Jump32,
              0x89:self.NOPi,
              0x8a:self.Call32,
              0x8b:self.AddCat32,
              0x8f:self.Haze,
              0x93:self.NOPh,
              0x95:self.CrashIndirect,
              0x96:self.CrashStart,
              0x9e:self.Interpolate,
              0x9f:self.NOPi,
              0xa0:self.Object,
              0xa7:self.SpriteVICall,
              0xa8:self.TextureRoadStart,
              0xaa:self.NewRunway,
              0xad:self.Animate,
              0xae:self.TransformEnd,
              0xac:self.NOPh,
              0xaf:self.TransformMatrix,
              0xb1:self.Tag,
              0xb2:self.Light,
              0xb3:self.IfInF1,
              0xb4:self.NOPi,
              0xb5:self.VertexList,
              0xb6:self.MaterialList,
              0xb7:self.TextureList,
              0xb8:self.SetMaterial,
              0xb9:self.DrawTriList,
              0xba:self.DrawLineList,
              0xbc:self.NOPi,
              0xbd:self.NOP,
              0xc4:self.SetMatrixIndirect,
              }

        while True:
            pos=bgl.tell()
            if pos>=enda:
                if self.donight():
                    bgl.seek(start)
                    continue
                self.makeobjs()
                if pos>enda:
                    if self.debug: self.debug.write("!Overrun at %x enda=%x\n" % (pos, enda))
                    raise struct.error
                return
            (cmd,)=unpack('<H',bgl.read(2))
            if cmd==0 or (cmd==0x22 and not self.stack):
                if self.donight():
                    bgl.seek(start)
                    continue
                self.makeobjs()
                if self.debug:
                    self.debug.write("%x: cmd %02x\n" % (pos, cmd))
                    for i in range(1, len(self.matrix)):
                        self.debug.write("!Unbalanced matrix:\n%s\n" % (
                            self.matrix[i]))
                return
            elif cmd in cmds:
                if self.debug: self.debug.write("%x: cmd %02x %s\n" % (
                    pos, cmd, cmds[cmd].__name__))
                cmds[cmd]()
            elif self.donight():
                bgl.seek(start)
                continue
            else:
                self.makeobjs()	# Try to go with what we've got so far
                if self.debug: self.debug.write("!Unknown cmd %x at %x\n" % (cmd, pos))
                raise struct.error


    def donight(self):
        if self.neednight and self.vars[0x28c]!=4:
            self.vars[0x28c]=4
            self.dayobjdat=self.objdat
            self.daylinedat=self.linedat
            self.daylightdat=self.lightdat
            self.daypolydat=self.polydat
            self.objdat={}
            self.linedat={}
            self.lightdat={}
            self.polydat=[]
            self.complexity=1
            self.loc=None
            self.alt=0
            self.altmsl=0
            self.layer=None
            self.matrix=[None]
            self.scale=self.basescale
            self.stack=[]	# (return address, layer, pop matrix?)
            self.tex=[]
            self.mat=[[(0.5,0.5,0.5),(0,0,0),(0,0,0)]]	# [[a,s,e]]
            self.vtx=[]
            self.idx=[]	# Indices into vtx
            self.m=None	# Index into mat
            self.t=-1	# Index into tex
            return True
        return False

    def makekey(self, dotex):
        if (not dotex) or self.t==-1:
            tex=lit=None
        elif self.vars[0x28c]==4:
            tex=None
            lit=self.tex[self.t]
            # Look for _lm version, eg LIEE cittadella universitaria-dm_liee_44
            (src,ext)=splitext(basename(lit))
            litlit=findtex(src+'_lm', dirname(lit), True)
            if litlit: lit=litlit
            if self.haze: self.output.haze[lit]=self.haze
        else:
            tex=self.tex[self.t]
            if self.haze: self.output.haze[tex]=self.haze
            (src,ext)=splitext(basename(tex))
            lit=findtex(src+'_lm', dirname(tex), True)
            if lit and self.haze: self.output.haze[lit]=self.haze
        return (self.loc,self.layer,self.alt,self.altmsl,self.matrix[-1],self.scale,tex,lit)

    def SPnt(self):		# 06
        self.pnt=unpack('<hhh', self.bgl.read(6))

    def CPnt(self):		# 07
        (cx,cy,cz)=unpack('<hhh', self.bgl.read(6))
        key=self.makekey(False)
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat:
                self.pnt=(cx,cy,cz)
                return	# transparent
        if self.pnt:
            (sx,sy,sz)=self.pnt
        else:	# continuation
            if not key in self.linedat:
                self.pnt=(cx,cy,cz)
                return	# CPnt with no SPnt
            (vtx,idx,m)=self.linedat[key][-1]
            if m==mat[0]:
                idx.append(len(vtx))
                vtx.append((cx,cy,cz,0,0,0,0,0))
                self.linedat[key][-1]=(vtx,idx,m)
                self.checkmsl()
                return
            else:	# change of material - can't do continuation
                (sx,sy,sz,nx,ny,nz,tu,tv)=vtx[-1]

        if not key in self.linedat:
            self.linedat[key]=[]
        self.linedat[key].append(([(sx,sy,sz,0,0,0,0,0), (cx,cy,cz,0,0,0,0,0)],
                                  [0,1], mat[0]))
        self.checkmsl()
        self.pnt=None

    def Closure(self):		# 08
        count=len(self.idx)
        vtx=[]
        for i in range(count):
            (x,y,z,c,c,c,c,c)=self.vtx[self.idx[i]]
            vtx.append((x,y,z, 0,1,0, x*self.scale/256, z*self.scale/256))
        if self.makepoly(False, vtx):
            return
        self.idx=[]
        if self.concave:
            (vtx,idx)=subdivide(vtx)
            self.concave=False
        else:
            idx=[]
            for i in range(1,len(vtx)-1):
                idx.extend([0,i,i+1])
        key=self.makekey(True)
        if not key in self.objdat:
            self.objdat[key]=[]
        self.objdat[key].append(([(1,1,1), (0,0,0), (0,0,0)], vtx, idx, True))
        self.checkmsl()
        
        
    def Jump(self):		# 0d, 1b: IfInBoxRawPlane, 73: IfInBoxP
        (off,)=unpack('<h', self.bgl.read(2))
        if not off: raise struct.error	# infloop
        self.bgl.seek(off-4,1)

    def StrRes(self):		# 0f:StrRes, 10:CntRes
        (i,)=unpack('<H',self.bgl.read(2))
        self.idx.append(i)
        
    def SColor(self):	# 14:Scolor, 50:GColor, 51:NewLColor, 52:NewSColor
        (c,)=unpack('H', self.bgl.read(2))
        self.m=0
        self.mat=[[self.unicol(c), (0,0,0), (0,0,0)]]
        
    def TextureEnable(self):		# 17
        (c,)=unpack('<H', self.bgl.read(2))
        if not c:
            self.t=-1
        else:
            self.t=0

    def Texture(self):		# 18
        (c,x,c,y)=unpack('<4h', self.bgl.read(8))
        tex=self.bgl.read(14).rstrip(' \0')
        l=tex.find('.')
        if l!=-1:	# Sometimes formatted as 8.3 with spaces
            tex=tex[:l].rstrip(' \0')+tex[l:]
        self.tex=[findtex(tex, self.texdir)]
        self.t=0
        if self.debug: self.debug.write("%s\n" % basename(self.tex[0]))
        if x or y:
            if self.debug: self.debug.write("!Tex offsets %d,%d\n" % (x,y))
        
    def ResList(self):		# 1a
        (index,count)=unpack('<2H', self.bgl.read(4))
        if len(self.vtx)<index:
            self.vtx.extend([None for i in range(index-len(self.vtx))])
        for i in range(index,index+count):
            (x,y,z)=unpack('<3h', self.bgl.read(6))
            v=(x,y,z, 0,0,0, 0,0)
            if i==len(self.vtx):
                self.vtx.append(v)
            else:
                self.vtx[i]=v

    def IfInBoxRawPlane(self):	# 1b
        # Skip
        (off,)=unpack('<h', self.bgl.read(2))
        self.bgl.seek(off-4,1)
        
    def IfIn2(self):		# 1c
        var=[0,0]
        mins=[0,0]
        maxs=[0,0]
        (off, var[0], mins[0], maxs[0],
         var[1], mins[1], maxs[1])=unpack('<7h', self.bgl.read(14))
        for i in range(2):
            if var[i]==0x346:
                self.complexity=complexity(mins[i])
                if maxs[i]==4: maxs[i]=5	# bug in eg EGNT
            val=self.getvar(var[i])
            if val<mins[i] or val>maxs[i]:
                self.bgl.seek(off-22,1)
                break

    def Haze(self):		# 1e:Haze, 8f:Alpha
        # XXX Alpha (8f) Also has meaning for non-textured polygons
        (self.haze,)=unpack('<H', self.bgl.read(2))
        
    def TaxiMarkings(self):	# 1f
        # ignored - info should now be in FS2004-style BGL
        self.rrt=True
        (size,)=unpack('<H', self.bgl.read(2))
        self.bgl.seek(size-4,1)
        
    def FaceTTMap(self):	# 20:FaceTTMap, 7a:GFaceTTMap
        (count,nx,ny,nz,)=unpack('<H3h', self.bgl.read(8))
        nx=nx/32767.0
        ny=ny/32767.0
        nz=nz/32767.0
        self.bgl.read(4)
        vtx=[]
        for i in range(count):
            (idx,tu,tv)=unpack('<H2h', self.bgl.read(6))
            (x,y,z,c,c,c,c,c)=self.vtx[idx]
            vtx.append((x,y,z, nx,ny,nz, tu/255.0,tv/255.0))
        if self.makepoly(True, vtx):
            return
        if self.concave:
            (vtx,idx)=subdivide(vtx)
            self.concave=False
        else:
            idx=[]
            for i in range(1,len(vtx)-1):
                idx.extend([0,i,i+1])
        # Change order if necessary to face in direction of normal
        (x0,y0,z0,c,c,c,c,c)=vtx[0]
        (x1,y1,z1,c,c,c,c,c)=vtx[1]
        (x2,y2,z2,c,c,c,c,c)=vtx[2]
        (x,y,z)=cross((x1-x0,y1-y0,z1-z0), (x2-x0,y2-y0,z2-z0))
        if dot((x,y,z), (nx,ny,nz))>0:
            idx.reverse()
        key=self.makekey(True)
        if not key in self.objdat:
            self.objdat[key]=[]
        self.objdat[key].append(([(1,1,1),(0,0,0),(0,0,0)], vtx, idx, False))
        self.checkmsl()
        
    def IfIn3(self):		# 21
        var=[0,0,0]
        mins=[0,0,0]
        maxs=[0,0,0]
        (off, var[0], mins[0], maxs[0],
         var[1], mins[1], maxs[1],
         var[2], mins[2], maxs[2])=unpack('<10h', self.bgl.read(20))
        for i in range(3):
            if var[i]==0x346:
                self.complexity=complexity(mins[i])
                if maxs[i]==4: maxs[i]=5	# bug in eg EGNT
            val=self.getvar(var[i])
            if val<mins[i] or val>maxs[i]:
                self.bgl.seek(off-22,1)
                break

    def Return(self):		# 22
        (off,self.layer,pop)=self.stack.pop()
        if pop:
            self.matrix.pop()
            if self.debug: self.debug.write("Now\n%s\n" % self.matrix[-1])
        self.bgl.seek(off)

    def Call(self):		# 23:Call, 32:PerspectiveCall
        (off,)=unpack('<h', self.bgl.read(2))
        if not off: raise struct.error	# infloop
        self.stack.append((self.bgl.tell(),self.layer,False))
        self.bgl.seek(off-4,1)

    def IfIn1(self):		# 24
        (off, var, vmin, vmax)=unpack('<4h', self.bgl.read(8))
        if vmin>vmax:	# Sigh. Seen in TFFR
            foo=vmax
            vmax=vmin
            vmin=foo
        if var==0x346:
            self.complexity=complexity(vmin)
            if vmax==4: vmax=5	# bug in eg EGNT
        val=self.getvar(var)
        if val<vmin or val>vmax:
            self.bgl.seek(off-10,1)

    def SeparationPlane(self):	# 25
        # Used for animating distance. Skip
        (off,nx,ny,nz,dist)=unpack('<4hi', self.bgl.read(12))
        #self.stack.append((self.bgl.tell(),self.layer,self.matrix))
        #self.bgl.seek(off-14,1)

    def SetWrd(self):		# 26
        (var,val)=unpack('<2h',self.bgl.read(4))
        self.vars[var]=val

    def GResList(self):		# 29
        (index,count)=unpack('<2H', self.bgl.read(4))
        if len(self.vtx)<index:
            self.vtx.extend([None for i in range(index-len(self.vtx))])
        for i in range(index,index+count):
            (x,y,z,nx,ny,nz)=unpack('<6h', self.bgl.read(12))
            v=(x,y,z, nx/32767.0,ny/32767.0,nz/32767.0, 0,0)
            if i==len(self.vtx):
                self.vtx.append(v)
            else:
                self.vtx[i]=v

    def FaceT(self):		# 2a:GFaceT, 3e:FaceT
        (count,nx,ny,nz)=unpack('<H3h', self.bgl.read(8))
        if count<=4: self.concave=False	# Don't bother
        nx=nx/32767.0
        ny=ny/32767.0
        nz=nz/32767.0
        self.bgl.read(4)
        vtx=[]
        for i in range(count):
            (idx,)=unpack('<H', self.bgl.read(2))
            (x,y,z,c,c,c,c,c)=self.vtx[idx]
            vtx.append((x,y,z, nx,ny,nz, x*self.scale/256, z*self.scale/256))
        if count<3: return	# wtf?
        if self.m==None and self.makepoly(False, vtx):
            # If color defined then use it in preference to bitmap
            return
        if self.concave:
            (vtx,idx)=subdivide(vtx)
            self.concave=False
        else:
            idx=[]
            for i in range(1,len(vtx)-1):
                idx.extend([0,i,i+1])
        # Change order if necessary to face in direction of normal
        (x0,y0,z0,c,c,c,c,c)=vtx[0]
        (x1,y1,z1,c,c,c,c,c)=vtx[1]
        (x2,y2,z2,c,c,c,c,c)=vtx[2]
        (x,y,z)=cross((x1-x0,y1-y0,z1-z0), (x2-x0,y2-y0,z2-z0))
        if dot((x,y,z), (nx,ny,nz))>0:
            idx.reverse()
        # If color defined then use it in preference to bitmap
        if self.m!=None or self.t==-1:
            tex=None
            if self.m==None:
                mat=self.mat[0]
            else:
                mat=self.mat[self.m]
                if not mat: return	# transparent
        else:
            tex=self.tex[self.t]
            if self.haze: self.output.haze[tex]=self.haze
            mat=[(1,1,1), (0,0,0), (0,0,0)]
        key=self.makekey(tex)
        if not key in self.objdat:
            self.objdat[key]=[]
        self.objdat[key].append((mat, vtx, idx, False))
        self.checkmsl()
        
    def SColor24(self):		# 2d: SColor24, 2e: LColor24
        (r,a,g,b)=unpack('4B', self.bgl.read(4))
        self.m=0
        if a==0xf0:	# unicol
            self.mat=[[self.unicol(0xf000+r), (0,0,0), (0,0,0)]]
        #elif (a>=0xb3 and a<=0xb8) or (a>=0xe3 and a<=0xe8):
        #    # E0 = transparent ... EF=opaque. Same for B?
        #    self.mat=[[(r/255.0,g/255.0,b/255.0,0.25), (0,0,0,0), (0,0,0,0)]]
        elif (a>=0xb0 and a<=0xb7) or (a>=0xe0 and a<=0xe7):
            # Treat semi-transparent as fully transparent
            self.mat=[None]
        else:
            self.mat=[[(r/255.0,g/255.0,b/255.0), (0,0,0), (0,0,0)]]
        
    def Scale(self):		# 2f
        self.bgl.read(8)	# jump,range (LOD) (may be 0),size,reserved
        (scale,)=unpack('<I', self.bgl.read(4))
        self.scale=65536.0/scale
        (lat,lon,self.altmsl)=self.LLA()
        self.alt=0
        if self.debug: self.debug.write("AltMSL %s\n" % self.altmsl)
        self.loc=Point(lat,lon)
        if lat<0 and not self.output.hemi:
            self.output.hemi=1
            self.setseason()

    def Instance(self):		# 33
        (off,p,b,h)=unpack('<h3H', self.bgl.read(8))
        self.stack.append((self.bgl.tell(),self.layer,True))
        p=p*360/65536.0
        b=b*360/65536.0
        h=h*360/65536.0
        newmatrix=Matrix()
        newmatrix=newmatrix.headed(h)
        newmatrix=newmatrix.pitched(p)
        newmatrix=newmatrix.banked(b)
        if self.debug:
            self.debug.write("Instance\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        self.matrix.append(newmatrix)
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])
        self.bgl.seek(off-10,1)

    def SuperScale(self):	# 34
        self.bgl.read(6)	# jump,range (LOD) (may be 0),size
        (scale,)=unpack('<H', self.bgl.read(2))
        if scale>31:
            self.scale=65536.0/self.getvar(scale)
        else:
            self.scale=1.0/pow(2,16-scale)
        
    def PntRow(self):		# 35
        (sx,sy,sz,ex,ey,ez,count)=unpack('<6hH', self.bgl.read(14))
        if count>1:
            dx=(ex-sx)/(count-1.0)
            dy=(ey-sy)/(count-1.0)
            dz=(ez-sz)/(count-1.0)
        else:
            dx=dy=dz=0
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat: return	# transparent
        key=self.makekey(False)
        if not key in self.lightdat:
            self.lightdat[key]=[]
        for i in range(count):
            self.lightdat[key].append(((sx+i*dx,sy+i*dy,sz+i*dz), mat[0]))
        self.checkmsl()
        
    def Point(self):		# 37
        (x,y,z)=unpack('<3h', self.bgl.read(6))
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat: return	# transparent
        key=self.makekey(False)
        if not key in self.lightdat:
            self.lightdat[key]=[]
        self.lightdat[key].append(((x,y,z), mat[0]))
        self.checkmsl()

    def Concave(self):		# 38
        self.concave=True

    def IfMsk(self):		# 39
        (off, var)=unpack('<2h', self.bgl.read(4))
        (mask,)=unpack('<H', self.bgl.read(2))
        val=self.getvar(var)
        if val&mask==0:
            self.bgl.seek(off-8,1)

    def VInstance(self):	# 3b
        (off,var)=unpack('<hH', self.bgl.read(4))
        self.stack.append((self.bgl.tell(),self.layer,True))
        p=self.getvar(var)
        p=self.getvar(var)*360/65536.0
        b=self.getvar(var+2)*360/65536.0
        h=self.getvar(var+4)*360/65536.0
        newmatrix=Matrix()
        newmatrix=newmatrix.headed(h)
        newmatrix=newmatrix.pitched(p)
        newmatrix=newmatrix.banked(b)
        if self.debug:
            self.debug.write("VInstance\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])
        self.matrix.append(newmatrix)
        self.bgl.seek(off-6,1)

    def Position(self):		# 3c
        self.bgl.read(8)	# jump,range (LOD) (may be 0),size,reserved
        (lat,lon,self.altmsl)=self.LLA()
        self.alt=0
        if self.debug: self.debug.write("AltMSL %s\n" % self.altmsl)
        pt=Point(lat,lon)
        if self.loc:
            (x,y,z)=Matrix().headed(self.loc.headingto(pt)).rotate(0,0,self.loc.distanceto(pt))
            if self.matrix[-1]:
                if self.debug: self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.matrix[-1]=self.matrix[-1].offset(x,0,z)
            else:
                self.matrix[-1]=Matrix().offset(x,0,z)
            if self.debug:
                self.debug.write("New\n%s\n" % self.matrix[-1])
                self.debug.write("Now\n%s\n" % Matrix().offset(x,0,z))
        else:
            self.loc=pt
        self.checkmsl()

    def Texture2(self):		# 43
        (size,)=unpack('<H', self.bgl.read(2))
        self.bgl.read(8)	# 00, flags0, unicol
        # FFS nl2000 crew can't count - so stop when hit first '\0'
        #tex=self.bgl.read(size-12).rstrip(' \0')
        tex=''
        size=size-12
        while size:
            c=self.bgl.read(1)
            if c=='\0':
                # Hope we're not at end of area - cos this will overrun.
                while self.bgl.read(1)=='\0':
                    pass
                self.bgl.seek(-1, 1)        
                break
            tex=tex+c
            size=size-1
        self.tex=[findtex(tex.rstrip(), self.texdir)]
        if self.debug: self.debug.write("%s\n" % basename(self.tex[0]))
        self.t=0
        
    def TextureRunway(self):	# 42: PolygonRunway, 44:TextureRunway
        # ignored - info should now be in FS2004-style BGL
        self.old=True
        self.bgl.seek(62,1)	# SDK lies

    def PointVICall(self):	# 46
        (off,x,y,z,p,vp,b,vb,h,vh)=unpack('<4h6H', self.bgl.read(20))
        if not off: raise struct.error	# infloop
        #if self.debug: self.debug.write("PointVICall %d %d %d %d %d %d %d %d %d\n" % (x,y,z,p,vp,b,vb,h,vh))
        self.stack.append((self.bgl.tell(),self.layer,True))
        p=p*360/65536.0
        b=b*360/65536.0
        h=h*360/65536.0
        newmatrix=Matrix()
        newmatrix=newmatrix.offset(x,y,z)
        newmatrix=newmatrix.headed(h+self.getvar(vh))
        newmatrix=newmatrix.pitched(p+self.getvar(vp))
        newmatrix=newmatrix.banked(b+self.getvar(vb))
        if self.debug:
            self.debug.write("PointVICall\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        self.matrix.append(newmatrix)
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])
        if self.libname and h:
            self.billboard=(x,y,z)
            # XXX Implement me!
        self.bgl.seek(off-22,1)

    def Building(self):		# 49
        (info,codes,x,y,z,stories,
         size_x,size_z)=unpack('<8h', self.bgl.read(16))
        incx=incz=0
        heights=[stories*4,0,0,4]
        texs=[0,0,0,0]
        if info>=0:
            typ=(info>>3)&3
            texs=[[62,66,38,46,54,66,62,54][info&7],0,0,
                  [ 7,28, 8,26,30,28, 7,30][info&7],
                  [ 7,28, 8,26,30,28, 7,30][info&7],
                  [ 7,28, 8,26,30,28, 7,30][info&7]]
        else:
            # Custom texture - how does that work?
            typ=info&3
        if typ==1:
            roof=3	# slanty
        elif typ==2:
            roof=0
            incx=incz=pi*22.5/180
        else:
            roof=0
        self.output.gencount += 1
        name="%s-generic-%d.obj" % (asciify(self.srcfile[:-4]),
                                    self.output.gencount)
        if typ==3:
            obj=makegenmulti(name,self.layer, 8, size_x, size_z, heights, texs)
        else:
            obj=makegenquad(name,self.layer, size_x, size_z, incx, incz,
                            heights, texs, roof)
        self.output.objdat[name]=[obj]
        if self.matrix[-1]:
            heading=self.matrix[-1].heading()	# XXX not really
            # handle translation
            loc=self.loc.biased(self.matrix[-1].m[3][0]*self.scale,
                                -self.matrix[-1].m[3][2]*self.scale)
        else:
            heading=0
            loc=self.loc
        self.output.objplc.append((loc, heading, self.complexity, name, 1))
            
    def MoveL2G(self):		# 4d:MoveL2G, 4e:MoveG2L
        (to, fr)=unpack('<2H', self.bgl.read(4))
        self.vars[to]=self.getvar(fr)
        
    def SurfaceType(self):	# 55
        (sfc, x, z, alt)=unpack('<Hhhh', self.bgl.read(8))
        if sfc!=0: return
        # Smooth surface
        if self.matrix[-1]:
            heading=self.matrix[-1].heading()	# XXX not really
        else:
            heading=0
        length=m2f*x*self.scale
        width=m2f*z*self.scale
        if self.debug: self.debug.write("SurfaceType %d (%dx%d) %d\n" % (
            sfc, length, width, alt))
        #self.output.misc.append((10, self.loc, 'xxx %6.2f %6d 0000.0000 0000.0000 %4d 111111 %02d 0 0 0.25 0 0000.0000' % (heading, length, width, 15)))

    def TextureRepeat(self):	# 5d
        (x,c,y)=unpack('<3h', self.bgl.read(6))
        if x or y:
            if self.debug: self.debug.write("!Tex offsets %d,%d\n" % (x,y))
        
    def IfSizeV(self):		# 5f:IfSizeV, 6d:IfSizeH
        # Go for max detail and let X-Plane remove based on it's own heuristics
        (off, a, b)=unpack('<3h', self.bgl.read(6))

    def IfVis(self):		# 62
        # Go for max detail and let X-Plane remove based on it's own heuristics
        (off, count)=unpack('<hH', self.bgl.read(4))
        self.bgl.seek(2*count,1)

    def LibraryCall(self):	# 63
        (off,a,b,c,d)=unpack('<hIIII', self.bgl.read(18))
        name="%08x%08x%08x%08x" % (a,b,c,d)
        if self.libname:
            # recursive call in library
            self.output.log('Unsupported request for object %s in %s' % (name, self.comment))
            return
        if self.matrix[-1]:
            heading=self.matrix[-1].heading()	# XXX not really
            # handle translation
            loc=self.loc.biased(self.matrix[-1].m[3][0]*self.scale,
                                -self.matrix[-1].m[3][2]*self.scale)
        else:
            heading=0
            loc=self.loc
        if self.debug:
            self.debug.write("LibraryCall %s\n%s\n" % (name,self.matrix[-1]))
        self.output.objplc.append((loc, heading, self.complexity,
                                   name, round(self.scale,2)))
        if self.altmsl:
            pass
            #self.output.log('Absolute altitude (%sm) for object %s at (%10.6f, %11.6f) in %s' % (round(self.altmsl,2), name, self.loc.lat, self.loc.lon, self.comment))
        elif self.alt:
            self.output.log('Non-zero altitude (%sm) for object %s at (%10.6f, %11.6f) in %s' % (round(self.alt,2), name, self.loc.lat, self.loc.lon, self.comment))

    def RoadStart(self):	# 69
        (width,x,y,z)=unpack('<hhhh', self.bgl.read(8))
        self.linktype=('VEHICLE', width*self.scale, 'FALSE')
        if not (-1<=width*self.scale<=1):
            self.nodes.append(TaxiwayPoint(self.loc.biased(x*self.scale, z*self.scale)))

    def RoadCont(self):		# 6a:RoadCont, 6f:TaxiwayCont
        (x,y,z)=unpack('<hhh', self.bgl.read(6))
        (type, width, centerline)=self.linktype
        if type and not (-1<=width<=1):
            self.nodes.append(TaxiwayPoint(Point(self.nodes[-1].lat,self.nodes[-1].lon).biased(x*self.scale, z*self.scale)))
            self.links.append(TaxiwayPath(type, width, centerline,
                                          len(self.nodes)-2,len(self.nodes)-1))

    def RiverStart(self):	# 6b
        # ignored
        self.bgl.seek(8,1)
        
    def RiverCont(self):	# 6c
        # ignored
        self.bgl.seek(6,1)

    def TaxiwayStart(self):	# 6e
        (width,x,y,z)=unpack('<hhhh', self.bgl.read(8))
        self.linktype=('TAXI', width*self.scale, 'FALSE')
        self.nodes.append(TaxiwayPoint(self.loc.biased(x*self.scale, z*self.scale)))

    def AddCat(self):		# 74
        (off,cat)=unpack('<2h', self.bgl.read(4))
        self.stack.append((self.bgl.tell(),self.layer,False))
        if self.debug: self.debug.write("Layer %d\n" % cat)
        self.layer=cat
        self.bgl.seek(off-6,1)

    def ScaleAGL(self):		# 77
        self.bgl.read(8)	# jump,range (LOD) (may be 0),size,reserved
        (scale,)=unpack('<I', self.bgl.read(4))
        self.scale=65536.0/scale
        (lat,lon,self.alt)=self.LLA()
        self.altmsl=0
        self.loc=Point(lat,lon)
        if lat<0 and not self.output.hemi:
            self.output.hemi=1
            self.setseason()
        
    def ResPnt(self):		# 80
        (idx,)=unpack('<H', self.bgl.read(2))
        (x,y,z,c,c,c,c,c)=self.vtx[idx]
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat: return	# transparent
        key=self.makekey(False)
        if not key in self.lightdat:
            self.lightdat[key]=[]
        self.lightdat[key].append(((x,y,z), mat[0]))
        self.checkmsl()
        
    def Call32(self):		# 2b:AddObj32, 8a:Call32
        (off,)=unpack('<i', self.bgl.read(4))
        if not off: raise struct.error	# infloop
        self.stack.append((self.bgl.tell(),self.layer,False))
        self.bgl.seek(off-6,1)

    def AddCat32(self):		# 8b
        (off,cat)=unpack('<ih', self.bgl.read(6))
        if not off: raise struct.error	# infloop
        self.stack.append((self.bgl.tell(),self.layer,False))
        if self.debug: self.debug.write("Layer %d\n" % cat)
        self.layer=cat
        self.bgl.seek(off-6,1)

    def ReScale(self):		# 83
        self.bgl.read(6)	# jump,range (LOD) (may be 0),size
        (scale,)=unpack('<I', self.bgl.read(4))
        #print hex(self.bgl.tell()),self.scale, scale, 65536.0/scale, scale/65536.0
        self.scale=self.scale*65536.0/scale

    def Jump32(self):		# 88
        (off,)=unpack('<i', self.bgl.read(4))
        if not off: raise struct.error	# infloop
        self.bgl.seek(off-6,1)

    def CrashIndirect(self):	# 95
        # Ignore - we'll see the drawing code anyway
        self.bgl.read(8)

    def CrashStart(self):	# 96
        # Skip real crash code
        (off,)=unpack('<h', self.bgl.read(2))
        self.bgl.seek(off-4,1)
        
    def Interpolate(self):	# 9e
        # XXX ignored
        self.anim=True
        self.bgl.read(18)

    def Object(self):		# a0
        (size,typ)=unpack('<HH', self.bgl.read(4))
        roof=0
        if typ==4:
            # flat
            (size_x,size_z,
             bottom_texture,size_bot_y,tindex_bot_x,tindex_bot_z,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,tindex_win_z,
             top_texture,size_top_y,tindex_top_x,tindex_top_z,
             roof_texture,tindex_roof_x,tindex_roof_z)=unpack('<18H', self.bgl.read(36))
            roof=0
            size_x *= self.scale
            size_z *= self.scale
            incx=incz=0
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture]
        elif typ==7:
            # pointy
            (size_x,size_z,
             bottom_texture,size_bot_y,tindex_bot_x,tindex_bot_z,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,tindex_win_z,
             top_texture,size_top_y,tindex_top_x,tindex_top_z,
             roof_texture,tindex_roof_x,tindex_roof_z,size_roof_y,tindex_roof_y)=unpack('<20H', self.bgl.read(40))
            roof=1
            size_x *= self.scale
            size_z *= self.scale
            incx=incz=0
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y,self.scale*size_roof_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture]
        elif typ==6:
            # gabled
            (size_x,size_z,
             bottom_texture,size_bot_y,tindex_bot_x,tindex_bot_z,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,tindex_win_z,
             top_texture,size_top_y,tindex_top_x,tindex_top_z,
             roof_texture,tindex_roof_x,tindex_roof_z,size_roof_y,
             tindex_gable_y,gable_texture,tindex_gable_z)=unpack('<22H', self.bgl.read(44))
            roof=2
            size_x *= self.scale
            size_z *= self.scale
            incx=incz=0
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y,self.scale*size_roof_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture, gable_texture]
        elif typ==8:
            # slanty
            (size_x,size_z,
             bottom_texture,size_bot_y,tindex_bot_x,tindex_bot_z,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,tindex_win_z,
             top_texture,size_top_y,tindex_top_x,tindex_top_z,
             roof_texture,tindex_roof_x,tindex_roof_z,size_roof_y,
             tindex_gable_y,gable_texture,tindex_gable_z,
             face_texture,tindex_face_x,tindex_face_y)=unpack('<25H', self.bgl.read(50))
            roof=3
            size_x *= self.scale
            size_z *= self.scale
            incx=incz=0
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y,self.scale*size_roof_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture, gable_texture,face_texture]
        elif typ==9:
            # flat pyramid
            (base_size_x,base_size_z,top_size_x,top_size_z,
             bottom_texture,size_bot_y,tindex_bot_x,tindex_bot_z,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,tindex_win_z,
             top_texture,size_top_y,tindex_top_x,tindex_top_z,
             roof_texture,tindex_roof_x,tindex_roof_z)=unpack('<20H', self.bgl.read(40))
            roof=0
            size_x=self.scale*base_size_x
            size_z=self.scale*base_size_z
            h2=2*(size_bot_y+size_win_y+size_top_y)
            incx=atan((base_size_x-top_size_x)/h2)
            incz=atan((base_size_z-top_size_z)/h2)
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture]
        elif typ in [10,11]:
            # pointy multi - note docs are incorrect
            (sides,spare,size_x,size_z,
             bottom_texture,size_bot_y,tindex_bot_x,
             window_texture,size_win_y,tindex_win_x,tindex_win_y,
             top_texture,size_top_y,tindex_top_x,
             roof_texture,size_roof_y,tindex_roof_x,tindex_roof_yz)=unpack('<BB16H', self.bgl.read(34))
            roof=1
            size_x *= self.scale
            size_z *= self.scale
            incx=incz=0
            heights=[self.scale*size_bot_y,self.scale*size_win_y,self.scale*size_top_y,self.scale*size_roof_y]
            texs=[bottom_texture, window_texture, top_texture, roof_texture]
        else:
            self.output.log('Unsupported effect at (%10.6f, %11.6f) in %s' % (self.loc.lat, self.loc.lon, self.comment))
            self.bgl.seek(size-6,1)
            return

        if self.matrix[-1]:
            heading=self.matrix[-1].heading()	# XXX not really
            # handle translation
            loc=self.loc.biased(self.matrix[-1].m[3][0]*self.scale,
                                -self.matrix[-1].m[3][2]*self.scale)
        else:
            heading=0
            loc=self.loc
        self.output.gencount += 1
        name="%s-generic-%d.obj" % (asciify(self.srcfile[:-4]),
                                    self.output.gencount)
        if typ in [10,11]:
            obj=makegenmulti(name,self.layer, sides, size_x, size_z, heights, texs)
        else:
            obj=makegenquad(name,self.layer, size_x, size_z, incx,incz,heights,texs,roof)
        self.output.objdat[name]=[obj]
        self.output.objplc.append((loc, heading, self.complexity, name, 1))
        if self.altmsl:
            pass
            #self.output.log('Absolute altitude (%sm) for generic building %s at (%10.6f, %11.6f) in %s' % (round(self.altmsl,2), name, self.loc.lat, self.loc.lon, self.comment))
        elif self.alt:
            self.output.log('Non-zero altitude (%sm) for generic building %s at (%10.6f, %11.6f) in %s' % (round(self.alt,2), name, self.loc.lat, self.loc.lon, self.comment))

    def SpriteVICall(self):	# a7
        (off,x,y,z,p,b,h,vp,vb,vh)=unpack('<4h6H', self.bgl.read(20))
        if not off: raise struct.error	# infloop
        self.stack.append((self.bgl.tell(),self.layer,self.matrix[-1]))
        newmatrix=Matrix()
        newmatrix=newmatrix.offset(x,y,z)
        if self.debug:
            self.debug.write("SpriteVICall\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        self.matrix.append(newmatrix)
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])
        if self.libname and h:
            self.billboard=(x,y,z)
            # XXX Implement me!
        self.bgl.seek(off-22,1)

    def TextureRoadStart(self):	# a8
        # width is in [m], ie not scaled
        (style,width,x,y,z)=unpack('<Hhhhh', self.bgl.read(10))
        if style<2 and width>=10:	# arbitrary
            self.linktype=('VEHICLE', width, 'TRUE')
        elif style<2:
            self.linktype=('VEHICLE', width, 'FALSE')
        elif style==2:
            self.linktype=('VEHICLE', width, 'TRUE')
        elif style==3:
            self.linktype=('VEHICLE', width, 'FALSE')
        else:	# railroad or river
            self.rrt=True
            self.linktype=(None, width, 'FALSE')
            return
        if not (-1<=width<=1):
            self.nodes.append(TaxiwayPoint(self.loc.biased(x*self.scale, z*self.scale)))
        
    def NewRunway(self):	# aa
        # runways should now be in FS2004-style BGL. But this command is
        # sometimes used to put back lights on an excluded runway
        (size,op)=unpack('<HB', self.bgl.read(3))
        endop=self.bgl.tell()+size-5
        (lat,lon,alt)=self.LLA()
        cloc=Point(lat,lon)
        (heading, length, width, markers, surface_type, surface_lights, identifiers)=unpack('<HHHHBBB', self.bgl.read(11))
        heading=heading*(360.0/65536)
        length=length/m2f	# includes displaced threshold
        width=width/m2f
        displaced=[0,0]
        overrun=[0,0]
        if surface_type==9:	# Water - ignore
            self.bgl.seek(endop)
            return
        elif surface_type==255:	# Transparent
            surface=15
        elif surface_type>8:
            surface=1
        else:
            surface=[4,2,1,3,5,5,1,2,14][surface_type]
        if markers&0x80 and surface<=2:
            shoulder=surface
        else:
            shoulder=0
        smoothing=0.25
        if surface_lights&3:
            centrelights=1
        else:
            centrelights=0
        if surface_lights&0xC:
            edgelights=2	# LOW and HIGH not supported in 8.50
        else:
            edgelights=0
        distance=0
        loc=[cloc.biased(-sin(radians(heading))*length/2,
                         -cos(radians(heading))*length/2),
             cloc.biased( sin(radians(heading))*length/2,
                          cos(radians(heading))*length/2)]
        number=["%02d" % (identifiers&63), "%02d" % (((identifiers&63)+18)%36)]
        if number[0]=='00': number[0]='36'
        if number[1]=='00': number[1]='36'
        number[0]=number[0]+[' ','L','R','C'][identifiers/64]
        number[1]=number[1]+[' ','R','L','C'][identifiers/64]
        angle=[3,3]
        if markers&0x44:	# precision or touchdown
            markings=[3,3]
        elif markers&2:		# threshold
            markings=[2,2]
        elif markers&0x30:	# ident or dashes
            markings=[1,1]
        else:
            markings=[0,0]            
        if markers&0x0800: markings[1]=0	# single end - no markings
        #if markers&0x1000: markings[0]=7	# not supported in 8.50
        if markers&0x1000: markings[0]=0	# base  closed - no markings
        #if markers&0x2000: markings[1]=7	# not supported in 8.50
        if markers&0x2000: markings[1]=0	# recip closed - no markings
        lights=[0,0]
        tdzl=[0,0]
        reil=[0,0]
        while self.bgl.tell()<endop:
            (op,foo)=unpack('<BB', self.bgl.read(2))
            if op==2:
                (foo,)=unpack('<H', self.bgl.read(2))
                displaced[0]=foo/m2f
            elif op==3:
                (foo,)=unpack('<H', self.bgl.read(2))
                displaced[1]=foo/m2f
            elif op==4 or op==8:
                (foo,)=unpack('<H', self.bgl.read(2))
                overrun[0]=foo/m2f
            elif op==5 or op==9:
                (foo,)=unpack('<H', self.bgl.read(2))
                overrun[1]=foo/m2f
            elif op==10 or op==11:
                (foo,)=unpack('<H', self.bgl.read(2))
                distance=1
            elif op==6 or op==7:
                (flags,system,strobes,vasi_system,vasi_angle,vasi_x,vasi_z,vasi_spacing)=unpack('<BBBBHHHH', self.bgl.read(12))
                # ignore vasi - hope it's specified in XML
                if flags&4:
                    reil[op-6]=1
                if flags&40:
                    tdzl[op-6]=1
                if system>10:
                    lights[op-6]=0
                else:
                    lights[op-6]=[0,11,9,8,6,5,1,1,12,3,4][system]
            else:
                self.bgl.seek(endop)
                if self.debug: self.debug.write("!Unknown NewRunway opcode %x\n" % op)
        # UK-style markings if Calvert approach lights
        for end in [0,1]:
            if lights[end] in [3,4] and markings[end] in [2,3]:
                markings[end]=markings[end]+2

        # Recalculate centre ignoring displaced thresholds
        clen=(displaced[0]+length-displaced[1])/2
        cloc=loc[0].biased(sin(radians(heading))*clen,
                           cos(radians(heading))*clen)
        txt="%5.2f %02d %02d %4.2f %d %d %d" % (width, surface, shoulder, smoothing, centrelights, edgelights, distance)
        for end in [0,1]:
            txt=txt+(" %-3s %10.6f %11.6f %5.1f %5.1f %02d %02d %d %d" % (number[end], loc[end].lat, loc[end].lon, displaced[end], overrun[end], markings[end], lights[end], tdzl[end], reil[end]))
        self.output.misc.append((100, cloc, [AptNav(100, txt)]))

    # opcodes ad to bd new in FS2002

    def Animate(self):		# ad
        # Just make a static translation matrix
        self.anim=True
        (c,c,c,c,x,y,z)=unpack('<4i3f', self.bgl.read(28))
        newmatrix=Matrix()
        newmatrix=newmatrix.offset(x,y,z)
        if self.debug:
            self.debug.write("Animate\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])
        self.matrix.append(newmatrix)

    def TransformEnd(self):	# ae
        self.matrix.pop()
        
    def TransformMatrix(self):	# af
        (x,y,z)=unpack('<3f', self.bgl.read(12))
        (q00,q01,q02, q10,q11,q12, q20,q21,q22)=unpack('<9f',self.bgl.read(36))
        newmatrix=Matrix([[q00,q01,q02,0],
                          [q10,q11,q12,0],
                          [q20,q21,q22,0],
                          [x,y,z,1]])
        if self.debug:
            self.debug.write("TransformMatrix\n")
            if self.matrix[-1]:
                self.debug.write("Old\n%s\n" % self.matrix[-1])
                self.debug.write("New\n%s\n" % newmatrix)
        if self.matrix[-1]:
            newmatrix=newmatrix*self.matrix[-1]
        self.matrix.append(newmatrix)
        if self.debug:
            self.debug.write("Now\n%s\n" % self.matrix[-1])

    def Tag(self):	# b1
        self.bgl.read(20).rstrip(' \0')	# what's this for?
        
    def Light(self):		# b2
        (type,x,y,z,intens,i,i,b,g,r,a,i,i,i)=unpack('<HfffIffBBBBfff',
                                                     self.bgl.read(42))
        # Typical intensities are 20 and 40 - so say 40=max
        if intens<40:
            intens=intens/(40.0*255.0)
        else:
            intens=1/255.0
        key=self.makekey(False)
        if not key in self.lightdat:
            self.lightdat[key]=[]
        self.lightdat[key].append(((x,y,z), (r*intens,g*intens,b*intens)))
        self.checkmsl()
        
    def IfInF1(self):		# b3
        (off, var, vmin, vmax)=unpack('<2h2f', self.bgl.read(12))
        if vmin>vmax:	# Sigh. Seen in TFFR
            foo=vmax
            vmax=vmin
            vmin=foo
        if var==0x346:
            self.complexity=complexity(vmin)
            if vmax==4: vmax=5	# bug in eg EGNT
        val=self.getvar(var)
        if val<vmin or val>vmax:
            self.bgl.seek(off-10,1)

    def VertexList(self):	# b5
        self.vtx=[]
        (count,)=unpack('<H', self.bgl.read(2))
        self.bgl.read(4)
        for i in range(count):
            self.vtx.append(unpack('<8f', self.bgl.read(32)))

    def MaterialList(self):	# b6
        self.mat=[]
        self.m=None
        (count,)=unpack('<H', self.bgl.read(2))
        self.bgl.read(4)
        for i in range(count):
            (dr,dg,db,da)=unpack('<4f', self.bgl.read(16))
            (ar,ag,ab,aa)=unpack('<4f', self.bgl.read(16))
            # average of diffuse & ambient
            #m=[((dr+ar)/2, (dg+ag)/2, (db+ab)/2)]
            m=[(dr, dg, db)]		# just use diffuse - discard ambient
            for j in range(2):		# specular and emissive
                (r,g,b,a)=unpack('<4f', self.bgl.read(16))
                m.append((r,g,b))
            self.bgl.read(4)		# power
            if da<0.5:
                self.mat.append(None)	# transparent
            else:
                self.mat.append(m)

    def TextureList(self):	# b7
        self.tex=[]
        self.t=-1
        (count,)=unpack('<H', self.bgl.read(2))
        self.bgl.read(4)
        for i in range(count):
            cls=unpack('<I', self.bgl.read(4))
            self.bgl.read(12)
            self.tex.append(findtex(self.bgl.read(64).rstrip(' \0'), self.texdir))

    def SetMaterial(self):	# b8
        (self.m,self.t)=unpack('<2h', self.bgl.read(4))
        if self.m>=len(self.mat):
            if self.debug:
                self.debug.write("Bad material %d/%d\n"%(self.m,len(self.mat)))
            self.m=0
        if self.t>=len(self.tex):
            if self.debug:
                self.debug.write("Bad texture %d/%d\n" %(self.t,len(self.tex)))
            self.t=-1
        if self.debug and self.t>=0:
            self.debug.write("%s\n" % basename(self.tex[self.t]))
        
    def DrawTriList(self):	# b9
        idx=[]
        (base,count,off)=unpack('<3H', self.bgl.read(6))
        for i in range(off/3):
            (a,b,c)=unpack('<3H', self.bgl.read(6))
            idx.extend([a+base,b+base,c+base])
        if self.makepoly(True, self.vtx, idx):
            return
        first=min(idx)
        last=max(idx)
        for i in range(len(idx)):
            idx[i]=idx[i]-first
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat: return	# transparent
        key=self.makekey(True)
        if not key in self.objdat:
            self.objdat[key]=[]
        self.objdat[key].append((mat, self.vtx[first:last+1], idx, False))
        self.checkmsl()

    def DrawLineList(self):	# ba
        idx=[]
        last=0
        first=maxint
        (base,count,off)=unpack('<3H', self.bgl.read(6))
        for i in range(off/2):
            (a,b)=unpack('<2H', self.bgl.read(4))
            idx.extend([a,b])
            first=min(first,a,b)
            last=max(last,a,b)
        for i in range(len(idx)):
            idx[i]=idx[i]-first
        if self.m==None:
            mat=self.mat[0]
        else:
            mat=self.mat[self.m]
            if not mat: return	# transparent
        key=self.makekey(False)
        if not key in self.linedat:
            self.linedat[key]=[]
        self.linedat[key].append((self.vtx[base+first:base+last+1],
                                  idx, mat[0]))
        self.checkmsl()
        
    # opcodes c0 and above new in FS2004

    def SetMatrixIndirect(self):	# c4
        # n=index into SCEN section of MDL file
        (scene,)=unpack('<H', self.bgl.read(2))
        pos=self.bgl.tell()
        self.matrix[-1]=Matrix()

        while scene!=-1:
            (child,peer,size,posa,parent)=self.scen[scene]
            self.bgl.seek(posa)		# Into ANIC section
            (cmd,src,dst)=unpack('<3H', self.bgl.read(6))
            if cmd==0xc6 and size==6:
                self.bgl.seek(self.tran+src*64)
                m=[]
                for j in range(4):
                    (a,b,c,d)=unpack('<4f',self.bgl.read(16))
                    m.append([a,b,c,d])
                # Matrices don't appear to nest - hence [-1]
                self.matrix[-1]=self.matrix[-1]*Matrix(m)
                if self.debug:
                    self.debug.write("Scene %d, %d %d:\n%s\n" % (
                        scene, src,dst, Matrix(m)))
            else:
                if self.debug:
                    self.debug.write("!Unsupported ANIC cmd %x, size %d\n" % (
                        cmd, size))
                self.anim=True
                break
            scene=parent

        if self.debug:
            self.debug.write("TransformIndirect:\n%s\n" % self.matrix[-1])
        self.bgl.seek(pos)


    # Ignored opcodes
    
    def NOP(self):
        # 02:NOOP, 05:Surface, 76:BGL, 7d:Perspective, bd:EndVersion
        pass

    def NOPh(self):
        # 30:Brightness, 3f:ShadowCall, 81:AntiAlias, 93: ???
        # ac:ZBias - XXX should generate poly_os n ?
        self.bgl.read(2)
        pass

    def NOPi(self):
        # 89:VarBase32, 9f:Override, b4: TextureSize, bc:BGLVersion
        self.bgl.read(4)
        pass


    # Helpers

    # helper to read lat, lon, alt
    def LLA(self):
        (lo,hi)=unpack('<Hi',self.bgl.read(6))
        if hi>=0:
            lat=hi+lo/65536.0
        else:
            lat=-(~hi+(~lo+1)/65536.0)
        lat=lat*360/cirp
        (lo,hi)=unpack('<Hi',self.bgl.read(6))
        if hi>=0:
            lon=hi+lo/65536.0
        else:
            lon=-(~hi+(~lo+1)/65536.0)
        lon=lon*360.0/0x100000000
        if lon>180: lon-=360
        
        (lo,hi)=unpack('<Hi',self.bgl.read(6))
        if hi>=0:
            alt=hi+lo/65536.0
        else:
            alt=-(~hi+(~lo+1)/65536.0)

        return (lat,lon,alt)


    # Try to make a draped polygon
    def makepoly(self, haveuv, vtx, idx=None):
        if self.t==-1: return False	# Only care about textured polygons
        if not self.loc: return False	# Not for library objects
        if self.debug: self.debug.write("Poly: %s %s " % (basename(self.tex[self.t]), self.alt))
        
        # Find unique points
        if idx:
            # Altitude test - Arbitrary. 0.124 used in UNNT
            yval=vtx[idx[0]][1]
            if not self.altmsl and yval*self.scale+self.alt>=0.125:
                if self.debug: self.debug.write("Above ground %s\n" % (yval*self.scale+self.alt))
                return False
            # Arrange points in order. Assumes all points are on the edge

            # Remove duplicates - O(n2) - eg EGPF Terraindetail.bmp
            #dump=(basename(self.tex[self.t])=='Terraindetail.bmp')
            if len(idx)<1000:	# arbitrary, gets too slow
                idx=list(idx)
                for i in range(len(idx)):
                    vi=vtx[idx[i]]
                    for j in range(i+1,len(idx)):
                        vj=vtx[idx[j]]
                        if vi[0]==vj[0] and vi[1]==vj[1] and vi[2]==vj[2] and vi[6]==vj[6] and vi[7]==vj[7]:
                            idx[j]=idx[i]                                
            
            allidx=unique(idx)	# unique set of points
            edges={}
            for i in range(0,len(idx),3):
                for j in range(3):
                    e=idx[i+j]
                    if vtx[e][1]!=yval:
                        if self.debug: self.debug.write("Not coplanar\n")
                        return False
                    if not e in edges: edges[e]=[]
                    if not idx[i+(j-1)%3] in edges[e]:
                        edges[e].append(idx[i+(j-1)%3])
                    if not idx[i+(j+1)%3] in edges[e]:
                        edges[e].append(idx[i+(j+1)%3])

            # West most vertex
            minx=maxint
            for i in allidx:
                if vtx[i][0]<minx:
                    minx=vtx[i][0]
                    bestidx=i
            myidx=[bestidx]
            allidx.remove(bestidx)
            thisheading=270

            while allidx:
                thisidx=bestidx
                thispoint=Point(vtx[thisidx][2], vtx[thisidx][0])
                bestidx=None
                bestheading=thisheading-360
                for i in edges[thisidx]:
                    if not i in allidx: continue
                    h=degrees(atan2(vtx[i][0]-vtx[thisidx][0],
                                    vtx[i][2]-vtx[thisidx][2]))
                    if h>thisheading: h=h-360
                    if h>bestheading:
                        bestidx=i
                        bestheading=h
                if bestidx==None:
                    if self.debug: self.debug.write("Disjoint\n")
                    return False
                myidx.append(bestidx)
                allidx.remove(bestidx)
                thisheading=(bestheading-180)%360-360
            vtx=[vtx[i] for i in myidx]
        elif not vtx:
            return False	# Eh?
        else:
            # Altitude test - Arbitrary. 0.124 used in UNNT
            yval=vtx[0][1]
            if not self.altmsl and yval*self.scale+self.alt>=0.125:
                if self.debug: self.debug.write("Above ground %s\n" % (yval*self.scale+self.alt))
                return False
            # Order must be CCW
            count=len(vtx)
            area2=0
            for i in range(count):
                if vtx[i][1]!=yval:
                    if self.debug: self.debug.write("Not coplanar\n")
                    return False
                area2+=(vtx[i][0]*vtx[(i+1)%count][2] - vtx[(i+1)%count][0]*vtx[i][2])
            if area2<0: vtx.reverse()	# Tested on SAEZ, LIRF

        # Trim textures that spill over edge
        TEXFUDGE=0.01
        minu=minv=maxint
        for (x,y,z, nx,ny,nz, tu,tv) in vtx:
            minu=min(minu,tu)
            minv=min(minv,tv)
        if minu%1 >= 1-TEXFUDGE:
            minu=floor(minu)+1
        else:
            minu=floor(minu)            
        if minv%1 >= 1-TEXFUDGE:
            minv=floor(minv)+1
        else:
            minv=floor(minv)

        # Bounding box
        points=[[]]
        minx=minz=maxint
        maxx=maxz=-maxint
        for (x,y,z, nx,ny,nz, tu,tv) in vtx:
            x=x*self.scale
            y=y*self.scale
            z=z*self.scale
            minx=min(minx,x)
            maxx=max(maxx,x)
            minz=min(minz,z)
            maxz=max(maxz,z)
            if self.matrix[-1]:
                (x,y,z)=self.matrix[-1].transform(x,y,z)
            if len(vtx)>4 and (tu-minu > 1+TEXFUDGE or tv-minv > 1+TEXFUDGE):
                if self.debug and haveuv: self.debug.write("Dropping textures - %s,%s\n" % (tu-minu,tv-minv))
                haveuv=False
            loc=self.loc.biased(x,z)
            points[0].append((loc,max(0,min(1,tu-minu)),max(0,min(1,tv-minv))))
    
        if not ((maxx-minx)>NM2m/16 or (maxz-minz)>NM2m/16):    # arbitrary
            if self.debug: self.debug.write("Too small %s %s\n" % (maxx-minx, maxz-minz))
            return False	# probably detail

        # Split EW
        while True:
            minlon=maxint
            maxlon=-maxint
            p=points[0]
            n=len(p)
            for i in range(n):
                (loc,tu,tv)=p[i]
                if loc.lon<minlon:
                    minlon=loc.lon
                    west=i
                if loc.lon>maxlon:
                    maxlon=loc.lon
            if maxlon<=floor(minlon)+1: break
            # Crosses tile boundary
            if self.debug: self.debug.write("Boundary EW: %s,%s " % (minlon,maxlon))
            for p1 in range(west,west+n):
                (loc,tu,tv)=p[p1%n]
                if loc.lon>floor(minlon)+1:
                    (ploc,ptu,ptv)=p[(p1-1)%n]
                    ratio=(floor(loc.lon)-ploc.lon)/(loc.lon-ploc.lon)
                    point1=(Point(ploc.lat+ratio*(loc.lat-ploc.lat),floor(loc.lon)),
                            ptu+ratio*(tu-ptu), ptv+ratio*(tv-ptv))
                    #print ratio
                    #print (ploc.lat,ploc.lon,ptu,ptv)
                    #print (loc.lat,loc.lon,tu,tv)
                    #print (point1[0].lat,point1[0].lon,point1[1],point1[2])
                    #print
                    break
            p1=p1%n
            for p2 in range(p1,p1+n):
                (loc,tu,tv)=p[p2%n]
                if loc.lon<=floor(minlon)+1:
                    (ploc,ptu,ptv)=p[(p2-1)%n]
                    ratio=(ploc.lon-floor(ploc.lon))/(ploc.lon-loc.lon)
                    point2=(Point(ploc.lat+ratio*(loc.lat-ploc.lat),floor(ploc.lon)),
                            ptu+ratio*(tu-ptu), ptv+ratio*(tv-ptv))
                    #print ratio
                    #print (ploc.lat,ploc.lon,ptu,ptv)
                    #print (loc.lat,loc.lon,tu,tv)
                    #print (point2[0].lat,point2[0].lon,point2[1],point2[2])
                    #print
                    break
            points.append([point2,point1]+[points[0][i%n] for i in range(p1,p2)])
            p2=p2%n
            if p1<p2: p1=p1+n
            points[0]=[points[0][i%n] for i in range(p2,p1)]+[point1,point2]

        # Split NS
        for pnt in range(len(points)):
            while True:
                minlat=maxint
                maxlat=-maxint
                p=points[pnt]
                n=len(p)
                for i in range(n):
                    (loc,tu,tv)=p[i]
                    if loc.lat<minlat:
                        minlat=loc.lat
                        south=i
                    if loc.lat>maxlat:
                        maxlat=loc.lat
                if maxlat<=floor(minlat)+1: break
                #print basename(self.tex[self.t]), minlat, maxlat, floor(minlat)+1
                #print n
                #for i in p: print "%s,%s" % (i[0].lat,i[0].lon)
                if self.debug: self.debug.write("Boundary NS: %s,%s " % (minlat,maxlat))
                for p1 in range(south,south+n):
                    (loc,tu,tv)=p[p1%n]
                    if loc.lat>floor(minlat)+1:
                        (ploc,ptu,ptv)=p[(p1-1)%n]
                        ratio=(floor(loc.lat)-ploc.lat)/(loc.lat-ploc.lat)
                        point1=(Point(floor(loc.lat),ploc.lon+ratio*(loc.lon-ploc.lon)),
                                ptu+ratio*(tu-ptu), ptv+ratio*(tv-ptv))
                        break
                p1=p1%n
                #print "%d: %s,%s" % (p1, p[p1][0].lat,p[p1][0].lon)
                for p2 in range(p1,p1+n):
                    (loc,tu,tv)=p[p2%n]
                    #print p2, loc.lat<=floor(minlat)+1
                    if loc.lat<=floor(minlat)+1:
                        (ploc,ptu,ptv)=p[(p2-1)%n]
                        ratio=(ploc.lat-floor(ploc.lat))/(ploc.lat-loc.lat)
                        point2=(Point(floor(ploc.lat),ploc.lon+ratio*(loc.lon-ploc.lon)),
                                ptu+ratio*(tu-ptu), ptv+ratio*(tv-ptv))
                        break
                points.append([point2,point1]+[points[pnt][i%n] for i in range(p1,p2)])
                p2=p2%n
                if p1<p2: p1=p1+n
                points[pnt]=[points[pnt][i%n] for i in range(p2,p1)]+[point1,point2]
        if haveuv:
            heading=65535
        elif self.matrix[-1] and self.matrix[-1].m[1][1]==1:	# No pitch or bank?
            heading=self.matrix[-1].heading()
        else:
            heading=0
        # handle day&night properly (eg spotlights)
        if self.vars[0x28c]==4:
            tex=None
            lit=self.tex[self.t]
            # Look for _lm version, eg LIEE cittadella universitaria-dm_liee_44
            (src,ext)=splitext(basename(lit))
            litlit=findtex(src+'_lm', dirname(lit), True)
            if litlit: lit=litlit
            if self.haze: self.output.haze[lit]=self.haze
        else:
            tex=self.tex[self.t]
            if self.haze: self.output.haze[tex]=self.haze
            (src,ext)=splitext(basename(tex))
            lit=findtex(src+'_lm', dirname(tex), True)
            if lit and self.haze: self.output.haze[lit]=self.haze
        for p in points:
            self.polydat.append((p, self.layer, heading, int(self.scale*256), tex, lit))
        if self.debug: self.debug.write("OK %s %s\n" % (maxx-minx, maxz-minz))
        return True


    # Generate Objects for the current Area or Library object
    def makeobjs(self):

        if self.neednight:
            # Merge day & night objects, removing dupes
            for lkey in self.daylightdat.keys():
                if lkey in self.lightdat:
                    for thing in self.daylightdat[lkey]:
                        if not thing in self.lightdat[lkey]:
                            self.lightdat[lkey].append(thing)
                else:
                    self.lightdat[lkey]=self.daylightdat[lkey]
            for lkey in self.daylinedat.keys():
                if lkey in self.linedat:
                    for thing in self.daylinedat[lkey]:
                        if not thing in self.linedat[lkey]:
                            self.linedat[lkey].append(thing)
                else:
                    self.linedat[lkey]=self.daylinedat[lkey]

            nightpolydat=self.polydat
            self.polydat=[]
            i=0
            while i<len(self.daypolydat):
                (points, layer, heading, scale, tex, lit)=self.daypolydat[i]
                #dump=tex and 'CONCRET2' in tex
                #if dump: print "day:", self.daypolydat[i]
                for j in range(len(nightpolydat)):
                    (npoints, nlayer, nheading, nscale, ntex, nlit)=nightpolydat[j]
                    #if dump: print nightpolydat[j]
                    if len(points)!=len(npoints) or layer!=nlayer or heading!=nheading or scale!=nscale: continue
                    #if dump: print "here"
                    for k in range(len(points)):
                        if points[k][0].lat!=npoints[k][0].lat or points[k][0].lon!=npoints[k][0].lon or points[k][1]!=npoints[k][1] or points[k][2]!=npoints[k][2]:
                            break
                    else:
                        #if dump: print "here2"
                        if tex==nlit:
                            self.polydat.append((points, layer, heading, scale, tex, None))
                        else:
                            self.polydat.append((points, layer, heading, scale, tex, nlit))
                        self.daypolydat.pop(i)
                        nightpolydat.pop(j)
                        break
                else:
                    i+=1
            self.polydat.extend(self.daypolydat)	# Day-only polys
            self.polydat.extend(nightpolydat)		# Night-only polys

            nightobjdat=self.objdat
            self.objdat={}
            for lkey in self.dayobjdat.keys():
                (loc, layer, alt, altmsl, matrix, scale, tex, lit)=lkey
                #dump=tex and 'EZEMAINX' in tex
                #if dump: print "day:", lkey
                for nkey in nightobjdat.keys():
                    (nloc,nlayer,nalt,naltmsl,nmatrix,nscale,ntex,nlit)=nkey
                    #if dump: print nkey
                    if (loc and loc.lat)==(nloc and nloc.lat) and (loc and loc.lon)==(nloc and nloc.lon) and layer==nlayer and alt==nalt and altmsl==naltmsl and (matrix and matrix.m)==(nmatrix and nmatrix.m) and scale==nscale:
                        # Extract objects in both day & night
                        #if dump: print "here"
                        if tex==nlit:
                            bkey=(loc,layer,alt,altmsl,matrix,scale,tex,None)
                        else:
                            bkey=(loc,layer,alt,altmsl,matrix,scale,tex,nlit)
                        i=0
                        while i<len(self.dayobjdat[lkey]):
                            thing=self.dayobjdat[lkey][i]
                            if thing in nightobjdat[nkey]:
                                if not bkey in self.objdat:
                                    self.objdat[bkey]=[]
                                self.objdat[bkey].append(thing)
                                self.dayobjdat[lkey].pop(i)
                                nightobjdat[nkey].remove(thing)
                            else:
                                i+=1
                        if not nightobjdat[nkey]:
                            nightobjdat.pop(nkey)
                        if not self.dayobjdat[lkey]:
                            self.dayobjdat.pop(lkey)
                            break
                if lkey not in self.dayobjdat: continue

                # check for same vertices but moved textures. 2 cases:
                # same day&night tex (eg SAEZ EZEMAINX) - just do day
                # diff day&night tex - do both (assume tex changes are boring) 
                for nkey in nightobjdat.keys():
                    (nloc,nlayer,nalt,naltmsl,nmatrix,nscale,ntex,nlit)=nkey
                    #if dump: print nkey
                    if (loc and loc.lat)==(nloc and nloc.lat) and (loc and loc.lon)==(nloc and nloc.lon) and layer==nlayer and alt==nalt and altmsl==naltmsl and (matrix and matrix.m)==(nmatrix and nmatrix.m) and scale==nscale:
                        #if dump: print "here2"
                        if tex==nlit:
                            bkey=(loc,layer,alt,altmsl,matrix,scale,tex,None)
                        else:
                            bkey=(loc,layer,alt,altmsl,matrix,scale,tex,nlit)
                        i=0
                        while i<len(self.dayobjdat[lkey]):
                            (m, vtx, idx, dbl)=self.dayobjdat[lkey][i]
                            for j in range(len(nightobjdat[nkey])):
                                (nm, nvtx, nidx,ndbl)=nightobjdat[nkey][j]
                                if len(vtx)!=len(nvtx) or dbl!=ndbl: continue
                                for k in range(len(vtx)):
                                    if vtx[k][0]!=nvtx[k][0] or vtx[k][1]!=nvtx[k][1] or vtx[k][2]!=nvtx[k][2]: break
                                else:
                                    if not bkey in self.objdat:
                                        self.objdat[bkey]=[]
                                    self.objdat[bkey].append((m, vtx, idx,dbl))
                                    self.dayobjdat[lkey].pop(i)
                                    nightobjdat[nkey].pop(j)
                                    break
                            else:
                                i+=1
                        if not nightobjdat[nkey]:
                            nightobjdat.pop(nkey)
                        if not self.dayobjdat[lkey]:
                            self.dayobjdat.pop(lkey)
                            break                        

            self.objdat.update(self.dayobjdat)	# Day-only objects
            self.objdat.update(nightobjdat)	# Night-only objects
        
        if not self.lightdat and not self.linedat and not self.objdat and not self.polydat and not self.links:
            return	# Only contained non-scenery stuff
        elif self.libname:
            bname=self.libname
            if self.loc:
                if self.debug: self.debug.write("!Location given for library object\n")
                raise struct.error	# Code assumes no spurious location
        elif self.loc:
            bname=self.srcfile
            if bname.lower()[-4:]=='.bgl':
                bname=bname[:-4]
        else:
            # Must have a location for placement
            if self.debug: self.debug.write("!No location\n")
            raise struct.error

        # Do taxiways & roads
        if self.links:
            allnodes = [Node(t) for t in self.nodes]
            names=[TaxiwayName(None)]
            alllinks = [Link(p, 0, names) for p in self.links]
            # replace indices with references, and setup node links
            for l in alllinks:
                for i in [0,1]:
                    l.nodes[i]=allnodes[l.nodes[i]]
                    l.nodes[i].links.append(l)
            taxilayout(allnodes, alllinks, 0, self.output)

        # Do polygons
        for (points, layer, heading, scale, tex, lit) in self.polydat:
            if tex:
                (fname,ext)=splitext(basename(tex))
            else:
                (fname,ext)=splitext(basename(lit))
                if fname[-3:].lower()=='_lm': fname=fname[:-3]
            if not ext.lower() in ['.dds', '.bmp', '.png']:
                fname+=ext	# For *.xAF etc
            # Spaces not allowed in textures. Avoid Mac/PC interop problems
            fname=asciify(fname).replace(' ','_')
            poly=Polygon(fname+'.pol', tex, lit, heading==65535, scale, layer)
            if fname in self.output.polydat:
                iname=fname
                i=0
                while True:
                    # See if this is a duplicate
                    if i:
                        fname="%s-%d" % (iname, i)
                        poly.filename=fname+'.pol'
                    if not fname in self.output.polydat:
                        break	# no match - new object
                    if poly==self.output.polydat[fname]:
                        break	# matched - re-use this object
                    i+=1
                    
            self.output.polydat[fname]=poly
            self.output.polyplc.append((fname, heading, points))


        objdat={}	# [(tex, lit, vlight, vline, vt, idx, mattri)] by (loc, layer, altmsl, hdg)

        # Sort throught lights, lines and objects.
        # Lights & lines first so are combined with untextured objects.
        # Keys must be unique to avoid duplicates.
        # Matrix is applied here to allow for detection of data in a bgl
        # that is duplicated apart from by heading
        for lkey in unique(self.lightdat.keys()+self.linedat.keys()+self.objdat.keys()):
            (loc, layer, alt, altmsl, matrix, scale, tex, lit)=lkey
            if layer>=32: layer=None
            newmatrix=matrix
            heading=0
            
            if loc and matrix and matrix.m[1][1]==1:	# No pitch or bank?
                # Rotate at placement time in hope of commonality
                heading=matrix.heading()
                # unrotate translation
                (x,y,z)=Matrix().headed(-heading).rotate(
                    matrix.m[3][0], matrix.m[3][1], matrix.m[3][2])
                scale2=scale/2.0
                newmatrix=Matrix().offset(round(x+scale2-(x+scale2)%scale,3), round(y+scale2-(y+scale2)%scale,3), round(z+scale2-(z+scale2)%scale,3))	# round to nearest unit to encourage a match
                if self.debug:
                    if tex:
                        self.debug.write("New heading %6.2f, offset (%7.3f,%7.3f,%7.3f), for %s\n" % (heading, newmatrix.m[3][0], newmatrix.m[3][1], newmatrix.m[3][2], basename(tex)))
                    else:
                        self.debug.write("New heading %6.2f, offset (%7.3f,%7.3f,%7.3f), for None\n" % (heading, newmatrix.m[3][0], newmatrix.m[3][1], newmatrix.m[3][2]))

            if loc:
                okey=(loc.lat, loc.lon, layer, altmsl, heading)
            else:
                okey=(None, None, layer, altmsl, None)

            # Consolidate with other data with same tex and placement
            if okey in objdat:
                for i in range(len(objdat[okey])):
                    (otex,olit, vlight, vline, vt, idx, mattri)=objdat[okey][i]
                    if tex==otex and lit==olit:
                        objdat[okey].pop(i)
                        break
                else:
                    vlight=[]
                    vline=[]
                    vt=[]
                    idx=[]
                    mattri=[]
            else:
                objdat[okey]=[]
                vlight=[]
                vline=[]
                vt=[]
                idx=[]
                mattri=[]

            if lkey in self.lightdat:
                for ((x,y,z),(r,g,b)) in self.lightdat[lkey]:
                    if newmatrix:
                        (x,y,z)=newmatrix.transform(x,y,z)
                    vlight.append([x*scale,alt+y*scale,-z*scale, r,g,b])
                
            if lkey in self.linedat:
                for (vtx, i, (r,g,b)) in self.linedat[lkey]:
                    vbase=len(vline)
                    for v in vtx:
                        (x,y,z,nx,ny,nz,tu,tv)=v
                        if newmatrix:
                            (x,y,z)=newmatrix.transform(x,y,z)
                        vline.append([x*scale,alt+y*scale,-z*scale, r,g,b])
                    for j in i:
                        idx.append(vbase+j)

            if lkey in self.objdat:
                # Sort to minimise attribute changes
                #self.objdat[lkey].sort()
                for (m, vtx, i, dbl) in self.objdat[lkey]:

                    # replace materials with palette texture
                    if not tex and not lit:
                        (pu,pv)=rgb2uv(m[0])
                    
                    vbase=len(vt)
                    firsttri=len(idx)
    
                    for v in vtx:
                        (x,y,z,nx,ny,nz,tu,tv)=v
                        if newmatrix:
                            (x,y,z)=newmatrix.transform(x,y,z)
                            (nx,ny,nz)=newmatrix.rotate(nx,ny,nz)
                        # replace materials with palette texture
                        if not tex and not lit:
                            tu=pu
                            tv=pv
                        vt.append([x*scale,alt+y*scale,-z*scale, nx,ny,-nz, tu,tv])
                        
                    # Reverse order of tris
                    for j in range(0,len(i),3):
                        for k in range(2,-1,-1):
                            idx.append(vbase+i[j+k])
    
                    if mattri:
                        # Consolidate TRI commands if possible
                        (xm, xfirsttri, xlen, xdbl)=mattri[-1]
                        if m==xm and dbl==xdbl:
                            mattri[-1]=(m, xfirsttri, xlen+len(idx)-firsttri, dbl)
                            continue
                    mattri.append((m, firsttri, len(idx)-firsttri, dbl))

            if not vlight and not vline and not vt:
                continue	# Only contained non-scenery stuff

            objdat[okey].append((tex, lit, vlight, vline, vt, idx, mattri))

        # XXX combine lights/lines with any tex?

        # If altmsl adjust to ground level of all objects with same placement
        for okey in objdat:
            (lat, lon, layer, altmsl, heading)=okey
            if not altmsl: continue
            miny=maxint
            for (tex, lit, vlight, vline, vt, idx, mattri) in objdat[okey]:
                for v in vlight + vline + vt:
                    miny=min(miny,v[1])
            if not miny: continue	# already at ground level
            for (tex, lit, vlight, vline, vt, idx, mattri) in objdat[okey]:
                for v in vlight + vline + vt:
                    v[1]=v[1]-miny

        objs=[]
        for okey in objdat:
            (lat, lon, layer, altmsl, heading)=okey
            loc=Point(lat, lon)
            for (tex, lit, vlight, vline, vt, idx, mattri) in objdat[okey]:
                texname=tex
                litname=lit
                if tex or lit:
                    if tex:
                        (fname,ext)=splitext(basename(tex))
                    else:
                        (fname,ext)=splitext(basename(lit))
                        if fname[-3:].lower()=='_lm': fname=fname[:-3]
                    if not ext.lower() in ['.dds', '.bmp', '.png']:
                        fname+=ext	# For *.xAF etc
                    # Spaces not allowed in textures. Avoid Mac/PC interop problems
                    fname="%s-%s" % (asciify(bname),
                                     asciify(fname).replace(' ','_'))
                else:
                    fname=asciify(bname)
                    if vt: texname='Resources/FS2X-palette.png'
    
                # Check whether this object is a 'decal' and apply poly_os
                poly=0
                minx=minz=maxint
                maxx=maxz=maxy=-maxint
                if vt:
                    decal=True
                    for (x,y,z, nx,ny,nz, tu,tv) in vt:
                        minx=min(minx,x)
                        maxx=max(maxx,x)
                        maxy=max(maxy,y)
                        minz=min(minz,z)
                        maxz=max(maxz,z)
                        if y>=0.125:	# Arbitrary. 0.124 used in UNNT
                            decal=False
                    if decal:
                        if (maxx-minx)>NM2m/4 or (maxz-minz)>NM2m/4:    # arbitrary
                            poly=1	# probably orthophoto
                        else:
                            poly=2	# probably detail
                    
                # Finally build the object
                obj=Object(fname+'.obj', self.comment, texname, litname, layer, vlight, vline, vt,
                           idx, mattri, poly)
                if self.libname:
                    objs.append(obj)
                else:
                    # handle multiple objs with same tex at different locs
                    if fname in self.output.objdat:
                        iname=fname
                        i=0
                        while True:
                            # See if this is a duplicate
                            if i:
                                fname="%s-%d" % (iname, i)
                                obj.filename=fname+'.obj'
                            if not fname in self.output.objdat:
                                break	# no match - new object
                            if obj==self.output.objdat[fname][0]:
                                break	# matched - re-use this object
                            i+=1
                    
                    self.output.objdat[fname]=[obj]
                    self.output.objplc.append((loc, heading,
                                               self.complexity, fname, 1))
                    if self.debug and maxy>250:	# arbitrary
                        self.debug.write("!Ludicrous size for object %s\n" % fname)

        # Add objs to library with one name
        if self.libname and objs:
            self.output.objdat[self.libname]=objs


    def checkmsl(self):
        return self.altmsl
        if self.altmsl:
            self.output.log('Absolute altitude (%sm) for object at (%10.6f, %11.6f) in %s' % (round(self.altmsl,2), self.loc.lat, self.loc.lon, self.comment))
            #if self.altmsl>0: self.altmsl=False	# Don't report again for this object
            return True
        else:
            return False


    def getvar(self, var):
        if var in self.vars:
            val=self.vars[var]
            if var==0x28c: self.neednight=True
            return val
        else:
            if self.debug: self.debug.write('!Undefined variable 0x%04x\n'%var)
            return 0


    def setseason(self):
        day=[61,182,243,364]
        self.vars[0x38a]=day[self.output.season]	# zulu day in the year
        self.vars[0x6F8]=(self.output.season+1)%4	# season: 1=Spring
        if self.output.hemi:
            # Southern hemisphere
            self.vars[0x38a]=(self.vars[0x38a]+182)%364
            self.vars[0x6F8]=(self.vars[0x6F8]+2)%4


    def unicol(self, c):
        cols={0xF000: (24, 24, 24),
              0xF001: (56, 56, 56),
              0xF002: (121, 121, 121),
              0xF003: (203, 203, 203),
              0xF004: (255, 255, 255),
              0xF005: (252, 60, 60),
              0xF006: (60, 252, 60),
              0xF007: (0, 153, 230),
              0xF008: (252, 126, 0),
              0xF009: (252, 252, 0),
              0xF00A: (125, 105, 80),
              0xF00B: (225, 189, 144),
              0xF00C: (252, 99, 63),
              0xF00D: (153, 198, 81),
              0xF00E: (0, 58, 104),
              0xF00F: (255, 0, 0),
              0xF010: (64, 255, 64),
              0xF011: (0, 0, 192),
              0xF012: (0, 105, 105),
              0xF013: (255, 128, 0),
              0xF014: (255, 255, 0),
              0xF015: (228, 228, 228),
              0xF016: (228, 228, 228),
              0xF017: (84, 20, 20),
              0xF018: (20, 84, 20),
              0xF019: (0, 40, 84),
              0xF01A: (84, 42, 0),
              0xF01B: (84, 84, 0),
              0xF01C: (75, 63, 48),
              0xF01D: (75, 63, 48),
              0xF01E: (84, 33, 21),
              0xF01F: (51, 66, 27),
              0xF020: (126, 30, 30),
              0xF021: (30, 126, 30),
              0xF022: (0, 71, 122),
              0xF023: (112, 56, 0),
              0xF024: (112, 112, 0),
              0xF025: (75, 63, 48),
              0xF026: (100, 84, 64),
              0xF027: (112, 44, 28),
              0xF028: (68, 88, 36),
              0xF029: (189, 45, 45),
              0xF02A: (45, 189, 45),
              0xF02B: (0, 112,179),
              0xF02C: (168, 84, 0),
              0xF02D: (168, 168, 0),
              0xF02E: (100, 84, 64),
              0xF02F: (150, 126, 96),
              0xF030: (168, 66, 42),
              0xF031: (102, 132, 54),
              0xF032: (82, 82, 82),
              0xF033: (163, 163, 163),
              0xF034: (196, 196, 196)}
        if c in cols:
            (r,g,b)=cols[c]
            return (r/255.0, g/255.0, b/255.0)
        else:
            return (0,0,0)


# Handle miscellaneous section 16
class ProcMisc:
    def __init__(self, bgl, srcfile, output, debug):
        self.bgl=bgl
        self.output=output
        self.debug=debug

        cmds={0x04:self.Marker,
              0x05:self.Marker,
              0x06:self.Marker,
              0x07:self.Landme,
              0x64:self.TimeZone,
              0x65:self.Platform,
              0x70:self.AreaSense,
              0xa6:self.Reserved,
              0xe6:self.Terrain,
              }

        while True:
            pos=bgl.tell()
            (cmd,)=unpack('<B',bgl.read(1))
            if cmd==0 or cmd==0x22:
                return
            elif cmd in cmds:
                if self.debug: self.debug.write("%x: cmd %02x %s\n" % (
                    pos, cmd, cmds[cmd].__name__))
                cmds[cmd]()
            else:
                if self.debug: self.debug.write("!Unknown s16 cmd %x at %x\n" %(cmd,pos))
                raise struct.error

    def Marker(self):		# 04,05,06
        # Ignore - this data should be in XML
        (size,)=unpack('<B',self.bgl.read(1))
        self.bgl.seek(size-2,1)

    def Landme(self):		# 07
        # Ignore
        (size,)=unpack('<B',self.bgl.read(1))
        self.bgl.seek(size-2,1)

    def TimeZone(self):		# 64
        # Ignore
        (size,)=unpack('<B',self.bgl.read(1))
        self.bgl.seek(size-2,1)

    def Platform(self):		# 65
        # Ignore
        (size,)=unpack('<B',self.bgl.read(1))
        self.bgl.seek(size-2,1)

    def AreaSense(self):	# 70
        # Assume inside
        (off,n)=unpack('<hH', self.bgl.read(4))
        self.bgl.seek(4*n,1)	# skip

    def Reserved(self):		# a6
        # Appears in section 16
        self.bgl.read(6)

    def Terrain(self):		# e6
        (foo,size,op,n,alt)=unpack("<BIHHi", self.bgl.read(13))
        l=[]
        for i in range(n):
            (lat,lon)=unpack("<ii", self.bgl.read(8))
            lat*=360.0/(65536*65536)
            lon*=360.0/(65536*65536)
            if lat>180: lon-=360
            if lon>180: lon-=360
            l.append(Point(lat, lon))
        # sort CCW
        area2=0
        for i in range(n):
            area2+=(l[i].lon * l[(i+1)%n].lat -
                    l[(i+1)%n].lon * l[i].lat)
        if area2<0: l.reverse()
        a=[AptNav(130, 'Flatten')]
        for i in range(n):
            a.append(AptNav(111, "%10.6f %11.6f" % (l[i].lat, l[i].lon)))
        a[-1].code=113
        if op==5:	# Flatten
            self.output.misc.append((130, l[0], a))
        elif self.debug:
            self.debug.write("!Unknown Terrain opcode %x\n" % op)


# Handle exception section 19
def ProcEx(bgl, output, debug):
    while True:
        (c,)=unpack('<B',bgl.read(1))
        if c==0:
            return
        elif c==3:
            # Exclusion
            (mask,n,s,e,w)=unpack('<H4I',bgl.read(18))
            if debug: debug.write("Exclude: %d\n" % mask)
            if mask&1:
                # objects
                n=n*360.0/cirp
                s=s*360.0/cirp
                e=e*360.0/0x100000000
                if e>180: e-=360
                w=w*360.0/0x100000000
                if w>180: w-=360
                output.exc.append(('obj', Point(s,w), Point(n,e)))
                #output.exc.append(('rwy', Point(s,w), Point(n,e)))
                #output.exc.append(('fac', Point(s,w), Point(n,e)))
        elif c==4:
            # Exception - ignore
            (lat,lon,typ,sn,sf,snf)=unpack('<IIBBBB',bgl.read(12))
            lat=lat*360.0/cirp
            lon=lon*360.0/0x100000000
            if lat>180: lat-=360
            if debug: debug.write("Exception: %d %x %x %x\n" % (typ,sn,sf,snf))
        else:
            if debug: debug.write("!Unknown s19 cmd: %x\n" % c)
            raise struct.error


# Handle terrain section 8
def ProcTerrain(bgl, srcfile, output, debug):
    LATRES=360.0/32768
    LONRES=480.0/32768
    
    (size,ver)=unpack('<2I', bgl.read(8))
    if size!=0x64 or ver!=0x202: raise struct.error
    (reserved1,)=unpack('<I', bgl.read(4))	# No idea how to decode this
    bgl.seek(11*4,1)
    (lwm,vtp)=unpack('<2I', bgl.read(8))
    if lwm or vtp: output.log('Skipping terrain data in file %s' % asciify(basename(srcfile)))
    if not reserved1: return

    texdir=normpath(join(dirname(srcfile), pardir))
    # For case-sensitive filesystems
    for d in listdir(texdir):
        if d.lower()=='texture':
            texdir=join(texdir, d)
            if texdir in output.photos: return
            break
    else:
        return

    for tex in glob(join(texdir, '[0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][0123][sS][uU].[bBdD][mMdD][pPsS]')):
        seasonal=glob(tex[:-6]+["[sS][pP]","[sS][uU]","[fF][aA]","[wW][iI]"][output.season]+".[bBdD][mMdD][pPsS]")
        if seasonal: tex=seasonal[0]
        # find NW point
        lat=lon=0
        for i in tex[-21:-6]:
            lat=lat+lat
            lon=lon+lon
            if i=='1': lon=lon+1
            elif i=='2': lat=lat+1
            elif i=='3':
                lat=lat+1
                lon=lon+1
        lat=90-lat*LATRES
        lon=lon*LONRES-180
        if debug: debug.write("%s: %s,%s\n" % (basename(tex), lat, lon))
        if lon+LONRES>floor(lon)+1:
            # Split EW
            points=[[(Point(lat-LATRES,lon),0,0),
                     (Point(lat-LATRES,floor(lon)+1),(floor(lon)+1-lon)/LONRES,0),
                     (Point(lat,floor(lon)+1),(floor(lon)+1-lon)/LONRES,1),
                     (Point(lat,lon),0,1)],
                    [(Point(lat-LATRES,floor(lon)+1),(floor(lon)+1-lon)/LONRES,0),
                     (Point(lat-LATRES,lon+LONRES),1,0),
                     (Point(lat,lon+LONRES),1,1),
                     (Point(lat,floor(lon)+1),(floor(lon)+1-lon)/LONRES,1)]]
        else:
            points=[[(Point(lat-LATRES,lon),0,0),
                     (Point(lat-LATRES,lon+LONRES),1,0),
                     (Point(lat,lon+LONRES),1,1),
                     (Point(lat,lon),0,1)]]
        if lat>floor(lat-LATRES)+1:
            # Split NS
            for i in range(len(points)):
                points.append([(Point(floor(lat-LATRES)+1,points[i][3].lon),points[i][3][1],(floor(lat-LATRES)+1-lat+LATRES)/LATRES),
                               (Point(floor(lat-LATRES)+1,points[i][2].lon),points[i][2][1],(floor(lat-LATRES)+1-lat+LATRES)/LATRES),
                               points[i][2], points[i][3]])
                points[i][2]=points[-1][1]
                points[i][3]=points[-1][0]

        name=basename(tex)[:-6]
        lit=findtex(basename(tex)[:-6]+'lm', texdir, True)
        poly=Polygon(name+'.pol', tex, lit, True, 1216, 0)
        output.polydat[name]=poly
        for p in points:
            output.polyplc.append((name, 65535, p))
    output.photos.append(texdir)


def subdivide(vtx):
    # Subdivide concave polygon into tris
    idx=[]
    count=len(vtx)
    
    if count<=4:
        # don't bother for quads
        for i in range(1,count-1):
            idx.extend([0,i,i+1])
        return (vtx, idx)
        
    planar=True
    ax=ay=az=au=av=0
    vx=[]
    vy=[]
    (c,y0,c,c,c,c,c,c)=vtx[0]
    for i in range(count):
        (x,y,z, nx,ny,nz, tu, tv)=vtx[i]
        if y!=y0:
            planar=False
        ax+=x
        ay+=y
        az+=z
        au+=tu
        av+=tv
        vx.append(x)
        vy.append(z)

    if not planar:
        # Just add a new vertex in the middle and use that in every triangle
        ax/=float(count)
        ay/=float(count)
        az/=float(count)
        for i in range(1,count-1):
            idx.extend([0,i,i+1])
        vtx.insert(0, (ax,ay,az, nx,ny,nz, au,av))
        idx.extend([0,count-1,count, 0,count,1])
        return (vtx, idx)

    # Simple O(n2) Greedy algorithm.
    # Remove candidate vertex if triangle formed by it and adjacent
    # vertices doesn't cross any edges.

    # Determine order
    area2=0
    for i in range(count):
        area2+=(vx[i]*vy[(i+1)%count] - vx[(i+1)%count]*vy[i])

    candidate=-1		# index of tested vertex
    count=len(vx)
    remaining=count
    vi=[True for i in range(count)]	# whether vertex is still a candidate
    edges=[]
    for i in range(count):
        edges.append((i,(i+1)%count))
    infloop=0

    # This needs to work for integer values of x and y
    while remaining>4:
        if infloop>count:
            # Shouldn't happen
            #if self.debug: self.debug.write('!InfLoop in polygon\n')
            return(vtx,idx)

        # Candidate and adjacent vertices
        candidate=(candidate+1)%count
        while not vi[candidate]: candidate=(candidate+1)%count
        p1=(candidate+1)%count
        while not vi[p1]: p1=(p1+1)%count
        p2=(candidate-1)%count
        while not vi[p2]: p2=(p2-1)%count

        # Is this triangle outside?
        a=0
        ii=[candidate, p1, p2]
        for i in range(3):
            a+=(vx[ii[i]]*vy[ii[(i+1)%3]] - vx[ii[(i+1)%3]]*vy[ii[i]])
        if area2*a<0:
            # this triangle no good
            infloop+=1
            continue

        # Does this triangle cross any edge (including those we've removed)?
        for edge in edges:
            (p3,p4)=edge
            if p3==p1 or p3==p2 or p4==p1 or p4==p2:
                continue
            d=(vy[p4]-vy[p3])*(vx[p2]-vx[p1])-(vx[p4]-vx[p3])*(vy[p2]-vy[p1])
            if d==0:
                continue	# parallel
            a=((vx[p4]-vx[p3])*(vy[p1]-vy[p3])-(vy[p4]-vy[p3])*(vx[p1]-vx[p3]))/d
            b=((vx[p2]-vx[p1])*(vy[p1]-vy[p3])-(vy[p2]-vy[p1])*(vx[p1]-vx[p3]))/d
            if a<0 or a>1 or b<0 or b>1:
                continue	# no intersection
            # intersection - this triangle no good
            infloop+=1
            break
        else:
            # No intersection - make triangle
            idx.extend([candidate, p1, p2])
            vi[candidate]=False
            edges.insert(0, (p2,p1))	# so tested first
            remaining-=1
            infloop=0

    p1=0
    while not vi[p1]: p1+=1
    p2=p1+1
    while not vi[p2]: p2+=1
    p3=p2+1
    while not vi[p3]: p3+=1
    p4=p3+1
    while not vi[p4]: p4+=1
    idx.extend([p1,p2,p3, p1,p3,p4])
    return(vtx,idx)


# Helper to return fully-qualified case-sensitive texture filename
def findtex(name, texdir, dropmissing=False):
    f=listdir(texdir)
    # Handle unicode
    if type(texdir)==types.UnicodeType:
        name=unicodeify(name)
        for i in range(len(f)):
            f[i]=normalize(f[i])
    # Extension is ignored by MSFS?
    (s,e)=splitext(name.lower())
    if len(s)==8 and s[-2]=='~' and s[-1].isdigit():
        # Crappy 8.3 name - pick first match
        s=s[:-2]
        crappy83=True
    else:
        crappy83=False
    for ext in [e, '.dds', '.bmp', '.r8']:
        # Fix case for case sensitive filesystems
        for i in f:
            if i.lower()==s+ext or (crappy83 and i.lower()[:-4].startswith(s) and i.lower()[-4:]==ext):
                return join(texdir, i)
    # Not found
    if dropmissing:
        return None
    else:
        return join(texdir, s+e)	# make lower-case to prevent dupes