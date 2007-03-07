#################################################################
#
#   Copyright (c) 2002 Zenoss, Inc. All rights reserved.
#
#################################################################

__doc__="""Device

Device is a base class that represents the idea of a single computer
system that is made up of software running on hardware.  It currently
must be IP enabled but maybe this will change.

$Id: Device.py,v 1.121 2004/04/23 19:11:58 edahl Exp $"""

__version__ = "$Revision: 1.121 $"[11:-2]

import sys
import re
import time
import types
import socket
import logging
log = logging.getLogger("zen.Device")

from _mysql_exceptions import OperationalError

from Products.ZenStatus import pingtree
from Products.ZenUtils.Graphics import NetworkGraph
from Products.ZenUtils.Utils import setWebLoggingStream, clearWebLoggingStream

# base classes for device
from ManagedEntity import ManagedEntity

from AccessControl import ClassSecurityInfo
from Globals import DTMLFile
from Globals import InitializeClass
from Acquisition import aq_base
from DateTime import DateTime
from App.Dialogs import MessageDialog

from ZODB.POSException import POSError
from AccessControl import Permissions as permissions

#from Products.SnmpCollector.SnmpCollector import findSnmpCommunity
from Products.DataCollector.ApplyDataMap import ApplyDataMap

from Products.ZenRelations.RelSchema import *
from Products.ZenUtils.IpUtil import isip
from Products.ZenEvents.ZenEventClasses import Status_Snmp
from MaintenanceWindow import DeviceMaintenanceWindow
from AdministrativeRole import DeviceAdministrativeRole
from UserCommand import UserCommand
from Commandable import Commandable

from OperatingSystem import OperatingSystem
from DeviceHW import DeviceHW

from ZenStatus import ZenStatus
from ZenDate import ZenDate
from Exceptions import *

def manage_createDevice(context, deviceName, devicePath="/Discovered",
            tag="", serialNumber="",
            zSnmpCommunity="", zSnmpPort=161, zSnmpVer="v1",
            rackSlot=0, productionState=1000, comments="",
            hwManufacturer="", hwProductName="",
            osManufacturer="", osProductName="",
            locationPath="", groupPaths=[], systemPaths=[],
            statusMonitors=["localhost"], performanceMonitor="localhost",
            discoverProto="snmp", priority=3):
    """Device factory creates a device and sets up its relations and collects
    its configuration.  SNMP Community discovery also happens here.  If an
    IP is passed for deviceName it will be used for collection and the device
    name will be set to the SNMP SysName (or ptr if SNMP Fails and ptr is valid)
    """
    if isip(deviceName):
        ip = deviceName
        deviceName = ""
        ipobj = context.getDmdRoot('Networks').findIp(ip)
        if ipobj:
            dev = ipobj.device()
            if dev:
                raise DeviceExistsError("Ip %s exists on %s" % (ip, deviceName))
    else:
        deviceName = context.prepId(deviceName)
        try: ip = socket.gethostbyname(deviceName)
        except socket.error: ip = ""
        if context.getDmdRoot("Devices").findDevice(deviceName):
            raise DeviceExistsError("Device %s already exists" % deviceName)
    if not ip:
        raise NoIPAddress("No IP found for name %s" % deviceName)
    if discoverProto == "snmp":
        zSnmpCommunity, zSnmpPort, zSnmpVer, snmpname = \
            findCommunity(context, ip, devicePath, zSnmpCommunity, zSnmpPort)
        log.debug("device community = %s", zSnmpCommunity)
        log.debug("device name = %s", snmpname)
        if not deviceName:
            try:
                if snmpname and socket.gethostbyname(snmpname):
                    deviceName = snmpname
            except socket.error: pass
            try:
                if (not deviceName and ipobj and ipobj.ptrName
                    and socket.gethostbyname(ipobj.ptrName)):
                    deviceName = ipobj.ptrName
            except socket.error: pass
            if not deviceName and snmpname:
                deviceName = snmpname
            if not deviceName:
                log.warn("unable to name device using ip '%s'", ip)
                deviceName = ip
    elif discoverProto == "command":
        raise ZenModelError("discover protocol 'ssh' not implemented yet")
    if not deviceName:
        deviceName = ip
    log.info("device name '%s' for ip '%s'", deviceName, ip)
    deviceClass = context.getDmdRoot("Devices").createOrganizer(devicePath)
    deviceName = context.prepId(deviceName)
    device = deviceClass.createInstance(deviceName)
    device.setManageIp(ip)
    device.manage_editDevice(
                tag, serialNumber,
                zSnmpCommunity, zSnmpPort, zSnmpVer,
                rackSlot, productionState, comments,
                hwManufacturer, hwProductName,
                osManufacturer, osProductName,
                locationPath, groupPaths, systemPaths,
                statusMonitors, performanceMonitor, priority)
    if discoverProto == "none":
        from Products.ZenModel.IpInterface import IpInterface
        tmpInterface = IpInterface('eth0')
        device.os.interfaces._setObject('eth0', tmpInterface)
        interface = device.getDeviceComponents()[0]
        interface.addIpAddress(device.getManageIp())
    return device


def findCommunity(context, ip, devicePath, community="", port=161):
    """Find the snmp community for an ip address using zSnmpCommunities.
    """
    try:
        from pynetsnmp.SnmpSession import SnmpSession
    except:
        from Products.DataCollector.SnmpSession import SnmpSession

    devroot = context.getDmdRoot('Devices').createOrganizer(devicePath)
    communities = []
    if community: communities.append(community)
    communities.extend(getattr(devroot, "zSnmpCommunities", []))
    port = getattr(devroot, "zSnmpPort", port)
    timeout = getattr(devroot, "zSnmpTimeout", 2)
    session = SnmpSession(ip, timeout=timeout, port=port)
    sysTableOid = '.1.3.6.1.2.1.1'
    oid = '.1.3.6.1.2.1.1.5.0'
    goodcommunity = ""
    devname = ""
    snmpver = "v1"
    for community in communities:
        session.community = community
        try:
            devname = session.get(oid).values()[0]
            goodcommunity = session.community
            break
        except (SystemExit, KeyboardInterrupt, POSError): raise
        except: pass #keep trying until we run out
    else:
        raise NoSnmp("no snmp found for ip = %s" % ip)
    return (goodcommunity, port, snmpver, devname)




def manage_addDevice(context, id, REQUEST = None):
    """make a device"""
    serv = Device(id)
    context._setObject(serv.id, serv)
    if REQUEST is not None:
        REQUEST['RESPONSE'].redirect(context.absolute_url()+'/manage_main')
                                     

addDevice = DTMLFile('dtml/addDevice',globals())


class Device(ManagedEntity, Commandable):
    """
    Device is a key class within zenoss.  It represents the combination of
    computer hardware running an operating system.
    """

    event_key = portal_type = meta_type = 'Device'
    
    default_catalog = "deviceSearch" #device ZCatalog

    relationshipManagerPathRestriction = '/Devices'

    manageIp = ""
    productionState = 1000
    snmpAgent = ""
    snmpDescr = ""
    snmpOid = ""
    snmpContact = ""
    snmpSysName = ""
    snmpLocation = ""
    rackSlot = 0
    comments = ""
    sysedgeLicenseMode = ""
    priority = 3

    _properties = ManagedEntity._properties + (
        {'id':'manageIp', 'type':'string', 'mode':'w'},
        {'id':'productionState', 'type':'keyedselection', 'mode':'w',
           'select_variable':'getProdStateConversions','setter':'setProdState'},
        {'id':'snmpAgent', 'type':'string', 'mode':'w'},
        {'id':'snmpDescr', 'type':'string', 'mode':''},
        {'id':'snmpOid', 'type':'string', 'mode':''},
        {'id':'snmpContact', 'type':'string', 'mode':''},
        {'id':'snmpSysName', 'type':'string', 'mode':''},
        {'id':'snmpLocation', 'type':'string', 'mode':''},
        {'id':'snmpLastCollection', 'type':'date', 'mode':''},
        {'id':'snmpAgent', 'type':'string', 'mode':''},
        {'id':'rackSlot', 'type':'int', 'mode':'w'},
        {'id':'comments', 'type':'text', 'mode':'w'},
        {'id':'sysedgeLicenseMode', 'type':'string', 'mode':''},
        {'id':'priority', 'type':'int', 'mode':'w'},
        )

    _relations = ManagedEntity._relations + (
        ("deviceClass", ToOne(ToManyCont, "DeviceClass", "devices")),
        ("termserver", ToOne(ToMany, "TerminalServer", "devices")),
        ("monitors", ToMany(ToMany, "StatusMonitorConf", "devices")),
        ("perfServer", ToOne(ToMany, "PerformanceConf", "devices")),
        ("location", ToOne(ToMany, "Location", "devices")),
        ("systems", ToMany(ToMany, "System", "devices")),
        ("groups", ToMany(ToMany, "DeviceGroup", "devices")),
        ("maintenanceWindows",ToManyCont(ToOne, "MaintenanceWindow", "productionState")),
        ("adminRoles", ToManyCont(ToOne,"AdministrativeRole","managedObject")),
        ('userCommands', ToManyCont(ToOne, 'UserCommand', 'commandable')),
        #("dhcpubrclients", ToMany(ToMany, "UBRRouter", "dhcpservers")),
        )

    # Screen action bindings (and tab definitions)
    factory_type_information = (
        {
            'id'             : 'Device',
            'meta_type'      : 'Device',
            'description'    : """Base class for all devices""",
            'icon'           : 'Device_icon.gif',
            'product'        : 'ZenModel',
            'factory'        : 'manage_addDevice',
            'immediate_view' : 'deviceStatus',
            'actions'        :
            (
                { 'id'            : 'status'
                , 'name'          : 'Status'
                , 'action'        : 'deviceStatus'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'osdetail'
                , 'name'          : 'OS'
                , 'action'        : 'deviceOsDetail'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'hwdetail'
                , 'name'          : 'Hardware'
                , 'action'        : 'deviceHardwareDetail'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'swdetail'
                , 'name'          : 'Software'
                , 'action'        : 'deviceSoftwareDetail'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'events'
                , 'name'          : 'Events'
                , 'action'        : 'viewEvents'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'historyEvents'
                , 'name'          : 'History'
                , 'action'        : 'viewHistoryEvents'
                , 'permissions'   : (permissions.view, )
                },
                { 'id'            : 'perfServer'
                , 'name'          : 'Perf'
                , 'action'        : 'viewDevicePerformance'
                , 'permissions'   : (permissions.view, )
                },
#                { 'id'            : 'perfConf'
#                , 'name'          : 'PerfConf'
#                , 'action'        : 'objRRDTemplate'
#                , 'permissions'   : ("Change Device", )
#                },
                { 'id'            : 'edit'
                , 'name'          : 'Edit'
                , 'action'        : 'editDevice'
                , 'permissions'   : ("Change Device",)
                },
#                { 'id'            : 'management'
#                , 'name'          : 'Manage'
#                , 'action'        : 'deviceManagement'
#                , 'permissions'   : ("Change Device",)
#                },
#                { 'id'            : 'custom'
#                , 'name'          : 'Custom'
#                , 'action'        : 'deviceCustomEdit'
#                , 'permissions'   : (permissions.view, )
#                },
#                { 'id'            : 'config'
#                , 'name'          : 'zProperties'
#                , 'action'        : 'zPropertyEdit'
#                , 'permissions'   : (permissions.view,)
#                },
#                { 'id'            : 'viewHistory'
#                , 'name'          : 'Changes'
#                , 'action'        : 'viewHistory'
#                , 'permissions'   : (permissions.view, )
#                },
            )
         },
        )

    security = ClassSecurityInfo()
    
    def __init__(self, id):
        ManagedEntity.__init__(self, id)
        os = OperatingSystem()
        self._setObject(os.id, os)
        hw = DeviceHW()
        self._setObject(hw.id, hw)
        #self.commandStatus = "Not Tested"
        self._lastPollSnmpUpTime = ZenStatus(0)
        self._snmpLastCollection = ZenDate('1968/1/8')
        self._lastChange = ZenDate('1968/1/8')


    def getRRDNames(self):
        return ['sysUpTime']


    def sysUpTime(self):
        try:
            return self.cacheRRDValue('sysUpTime', -1)
        except Exception:
            log.exception("failed getting sysUpTime")
            return -1


    def availability(self, *args, **kw):
        from Products.ZenEvents import Availability
        results = Availability.query(self.dmd, device=self.id, *args, **kw)
        if results:
            return results[0]
        else:
            return None


    def __getattr__(self, name):
        if name == 'lastPollSnmpUpTime':
            return self._lastPollSnmpUpTime.getStatus()
        elif name == 'snmpLastCollection':
            return self._snmpLastCollection.getDate()
        else:
            raise AttributeError, name


    def _setPropValue(self, id, value):
        """override from PerpertyManager to handle checks and ip creation"""
        self._wrapperCheck(value)
        if id == 'snmpLastCollection':
            self.setSnmpLastCollection(value)
        else:
            ManagedEntity._setPropValue(self, id, value)

    
    def applyDataMap(self, datamap, relname="", compname="", modname=""):
        """Apply a datamap passed as a list of dicts through XML-RPC.
        """
        adm = ApplyDataMap()
        adm.applyDataMap(self, datamap, relname=relname,
                         compname=compname, modname=modname)

    
    def traceRoute(self, target, ippath=None):
        if ippath is None: ippath=[]
        if not isip(target):
            target = self.findDevice(target)
            if not target: raise ValueError("target %s not found in dmd",target)
            target = target.getManageIp()
        return self.os.traceRoute(target, ippath)


    def getMonitoredComponents(self):
        """Return list of monitored DeviceComponents on this device.
        """
        return [c for c in self.getDeviceComponents() if c.monitored()]


    def getDeviceComponents(self):
        """Return list of all DeviceComponents on this device.
        """
        cmps = []
        cmps.extend(self.os.ipservices())
        cmps.extend(self.os.winservices())
        cmps.extend(self.os.interfaces())
        cmps.extend(self.os.filesystems())
        cmps.extend(self.os.processes())
        cmps.extend(self.hw.harddisks())
        return cmps

    def getSnmpConnInfo(self):
        return (self.id, 
                (self.manageIp, self.zSnmpPort),
                (self.zSnmpCommunity, self.zSnmpVer,
                 self.zSnmpTimeout, self.zSnmpTries))


    def getOSProcessConf(self):
        """Return process monitoring configuration.
        """
        procs = [ o.getOSProcessConf() for o in self.os.processes() \
                                            if o.monitored() ]
        if not procs: return None
        return (self.getSnmpConnInfo(), procs)


    def getSnmpOidTargets(self):
        """Return information for snmp collection on this device in the form
        (devname,
         (ip, snmpport),
         (snmpcommunity, snmpversion, snmptimeout, snmptries)
         [(name, oid, path, type, createCmd, thresholds),])
        """
        oids = (super(Device, self).getSnmpOidTargets())
        max = getattr(self, 'zMaxOIDPerRequest')
        for o in self.os.getMonitoredComponents():
            if o.meta_type != "OSProcess":
                oids.extend(o.getSnmpOidTargets())
        return (float(self.getLastChange()), self.getSnmpConnInfo(), oids, max)


    def getDataSourceCommands(self):
        """Return list of command definitions in the form
        (device, user, pass [(cmdinfo,),...])
        """
        cmds = (super(Device, self).getDataSourceCommands())
        for o in self.getMonitoredComponents():
            cmds.extend(o.getDataSourceCommands())
        if cmds:
            return (self.id, self.getManageIp(), self.zCommandPort,
                    self.zCommandUsername, self.zCommandPassword,
                    self.zCommandLoginTimeout, self.zCommandCommandTimeout,
                    self.zKeyPath,self.zMaxOIDPerRequest,
                    cmds)

    def getXmlRpcTargets(self):
        """Return information for xmlrpc collection on this device in the form
        (devname, xmlRpcStatus,
         (url, methodName),
         [(name, path, type, createCmd, thresholds)])
        """
        targets = (super(Device, self).getXmlRpcTargets())
        return (self.id, self.getXmlRpcStatus(), targets)


    def getRRDTemplate(self, name=None):
        """Return the closest RRDTemplate named name by walking our aq chain.
        """
        if not name: name = self.getRRDTemplateName()
        templ = getattr(self, name, None)
        if templ is None:
            templ = super(Device, self).getRRDTemplate(name)
        return templ

   
    def getHWManufacturerName(self):
        """Return the hardware manufacturer name of this device.
        """
        return self.hw.getManufacturerName()


    def getHWProductName(self):
        """Return the hardware product name of this device.
        """
        return self.hw.getProductName()


    def getHWProductKey(self):
        """Get our HW product by productKey.
        """
        return self.hw.getProductKey()


    def getOSManufacturerName(self):
        """Return the OS manufacturer name of this device.
        """
        return self.os.getManufacturerName()


    def getOSProductName(self):
        """Return the OS product name of this device.
        """
        return self.os.getProductName()


    def getOSProductKey(self):
        """Get our OS product by productKey.
        """
        return self.os.getProductKey()


    def setOSProductKey(self, prodKey):
        """Set our OS product by productKey.
        """
        self.os.setProductKey(prodKey)


    def setHWProductKey(self, prodKey):
        """Set our HW product by productKey.
        """
        self.hw.setProductKey(prodKey)


    def setHWSerialNumber(self, number):
        """Set our hardware serial number.
        """
        self.hw.serialNumber = number


    def getHWSerialNumber(self):
        """Return our hardware serial number.
        """
        return self.hw.serialNumber


    def followNextHopIps(self):
        """Return the ips that our indirect routs point to which 
        aren't currently connected to devices.
        """
        ips = []
        for r in self.os.routes():
            ipobj = r.nexthop()
            #if ipobj and not ipobj.device(): 
            if ipobj: ips.append(ipobj.id)
        return ips


    security.declareProtected('View', 'getLocationName')
    def getLocationName(self):
        """return the full location name ie /Location/SubLocation/Rack"""
        loc = self.location()
        if loc: return loc.getOrganizerName()
        return ""

    def getLocationLink(self):
        """Return an a link to the devices location.
        """
        loc = self.location()
        if loc: return "<a href='%s'>%s</a>" % (loc.getPrimaryUrlPath(),
                                                loc.getOrganizerName())
        return ""


    security.declareProtected('View', 'getSystemNames')
    def getSystemNames(self):
        """get the system names for this device"""
        return map(lambda x: x.getOrganizerName(), self.systems())


    security.declareProtected('View', 'getDeviceGroupNames')
    def getDeviceGroupNames(self):
        """get the device group names for this device"""
        return map(lambda x: x.getOrganizerName(), self.groups())


    security.declareProtected('View', 'getOsVersion')
    def getOsVersion(self):
        return self.os.version()


    security.declareProtected('View', 'getStatusMonitorNames')
    def getStatusMonitorNames(self):
        """return status monitor names"""
        return map(lambda x: x.getId(), self.monitors())

    
    security.declareProtected('View', 'getPerformanceServer')
    def getPerformanceServer(self):
        """return device performance server"""
        return self.perfServer()


    security.declareProtected('View', 'getPerformanceServerName')
    def getPerformanceServerName(self):
        """return device performance server"""
        cr = self.perfServer()
        if cr: return cr.getId()
        return ''


    security.declareProtected('View', 'getLastChange')
    def getLastChange(self):
        """Return DateTime of last change detected on this device.
        """
        return self._lastChange.getDate()

    
    security.declareProtected('View', 'getLastChangeString')
    def getLastChangeString(self):
        """Return date string of last change detected on this device.
        """
        return self._lastChange.getString()


    security.declareProtected('View', 'getSnmpLastCollection')
    def getSnmpLastCollection(self):
        return self._snmpLastCollection.getDate()

    
    security.declareProtected('View', 'getSnmpLastCollectionString')
    def getSnmpLastCollectionString(self):
        return self._snmpLastCollection.getString()


    security.declareProtected('Change Device', 'setManageIp')
    def setManageIp(self, ip="", REQUEST=None):
        """Set the manage ip, if ip is not passed perform DNS lookup.
        """
        if not ip:
            try: ip = socket.gethostbyname(self.id)
            except socket.error: ip = ""
        self.manageIp = ip
        if REQUEST:
            return self.callZenScreen(REQUEST)
        else:
            return self.manageIp



    security.declareProtected('View', 'getManageIp')
    def getManageIp(self):
        """Return the management ip for this device. 
        """
        return self.manageIp

    
    def getManageIpObj(self):
        """Return the management ipobject for this device.
        """
        if self.manageIp:
            return self.Networks.findIp(self.manageIp)

    
    security.declareProtected('View', 'getManageInterface')
    def getManageInterface(self):
        """Return the management interface of a device based on its manageIp.
        """
        ipobj = self.Networks.findIp(self.manageIp)
        if ipobj: return ipobj.interface()

    
    security.declareProtected('View', 'uptimeStr')
    def uptimeStr(self):
        '''return a textual representation of the snmp uptime'''
        ut = self.sysUpTime()
        if ut < 0:
            return "Unknown"
        elif ut == 0:
            return "0d:0h:0m:0s"
        ut = float(ut)/100.
        days = ut/86400
        hour = (ut%86400)/3600
        mins = (ut%3600)/60
        secs = ut%60
        return "%02dd:%02dh:%02dm:%02ds" % (
            days, hour, mins, secs)


    def getPeerDeviceClassNames(self):
        "build a list of all device paths that have the python class pyclass"
        dclass = self.getDmdRoot("Devices")
        return dclass.getPeerDeviceClassNames(self.__class__)


    def havePydot(self):
        """return true if pydot is installed.
        """
        try:
            import pydot
            return True
        except ImportError:
            return False


    security.declareProtected('View', 'getRouterGraph')
    def getRouterGraph(self):
        '''get a graph representing the relative routers'''
        node = pingtree.buildTree(self)
        g = NetworkGraph(node=node, parentName=self.id)
        #g.format = 'svg'
        self.REQUEST.RESPONSE.setHeader('Content-Type', 'image/%s' % g.format)
        return g.render()

    security.declareProtected('View', 'getNetworkGraph')
    def getNetworkGraph(self):
        '''
        get a graph representing the relative routers as well as the
        networks
        '''
        node = pingtree.buildTree(self)
        g = NetworkGraph(node=node, parentName=self.id)
        #g.format = 'svg'
        self.REQUEST.RESPONSE.setHeader('Content-Type', 'image/%s' % g.format)
        return g.render(withNetworks=True)
        
    ####################################################################
    # Edit functions used to manage device relations and other attributes
    ####################################################################

    security.declareProtected('Change Device', 'manage_snmpCommunity')
    def manage_snmpCommunity(self):
        """Reset the snmp community using the zSnmpCommunities variable.
        """
        try:
            zSnmpCommunity, zSnmpPort, zSnmpVer, snmpname = \
                findCommunity(self, self.manageIp, self.getDeviceClassPath(),
                            port=self.zSnmpPort)
        except NoSnmp:
            pass
        else:
            if self.zSnmpCommunity != zSnmpCommunity:
                self.setZenProperty("zSnmpCommunity", zSnmpCommunity)
            if self.zSnmpPort != zSnmpPort:
                self.setZenProperty("zSnmpPort", zSnmpPort)
            if self.zSnmpVer != zSnmpVer:
                self.setZenProperty("zSnmpVer", zSnmpVer)


    security.declareProtected('Change Device', 'manage_editDevice')
    def manage_editDevice(self,
                tag="", serialNumber="",
                zSnmpCommunity="", zSnmpPort=161, zSnmpVer="v1",
                rackSlot=0, productionState=1000, comments="",
                hwManufacturer="", hwProductName="",
                osManufacturer="", osProductName="",
                locationPath="", groupPaths=[], systemPaths=[],
                statusMonitors=["localhost"], performanceMonitor="localhost",
                priority=3, REQUEST=None):
        """edit device relations and attributes"""
        self.hw.tag = tag
        self.hw.serialNumber = serialNumber
        if self.zSnmpCommunity != zSnmpCommunity:
            self.setZenProperty("zSnmpCommunity", zSnmpCommunity)
        if self.zSnmpPort != zSnmpPort:
            self.setZenProperty("zSnmpPort", zSnmpPort)
        if self.zSnmpVer != zSnmpVer:
            self.setZenProperty("zSnmpVer", zSnmpVer)

        self.rackSlot = rackSlot
        self.setProdState(productionState)
        self.setPriority(priority)
        self.comments = comments

        if hwManufacturer and hwProductName:
            log.info("setting hardware manufacturer to %s productName to %s"
                            % (hwManufacturer, hwProductName))
            self.hw.setProduct(hwProductName, hwManufacturer)
        else:
            self.hw.productClass.removeRelation()

        if osManufacturer and osProductName:
            log.info("setting os manufacturer to %s productName to %s"
                            % (osManufacturer, osProductName))
            self.os.setProduct(osProductName, osManufacturer)
        else:
            self.os.productClass.removeRelation()

        if locationPath:
            log.info("setting location to %s" % locationPath)
            self.setLocation(locationPath)

        if groupPaths:
            log.info("setting group %s" % groupPaths)
            self.setGroups(groupPaths)

        if systemPaths:
            log.info("setting system %s" % systemPaths)
            self.setSystems(systemPaths)

        log.info("setting status monitor to %s" % statusMonitors)
        self.setStatusMonitors(statusMonitors)

        log.info("setting performance monitor to %s" % performanceMonitor)
        self.setPerformanceMonitor(performanceMonitor)
       
        self.setLastChange()
        if REQUEST:
            REQUEST['message'] = "Device Saved at time:"
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'manage_addMaintenanceWindow')
    def manage_addMaintenanceWindow(self, newId=None, REQUEST=None):
        "Add a Maintenance Window to this device"
        mw = None
        if newId:
            mw = DeviceMaintenanceWindow(newId)
            self.maintenanceWindows._setObject(newId, mw)
            self.setLastChange()
        if REQUEST:
            if mw:
                REQUEST['message'] = "Maintenace Window Added"
            return self.callZenScreen(REQUEST)
                          
    security.declareProtected('Change Device', 'manage_deleteMaintenanceWindow')
    def manage_deleteMaintenanceWindow(self, maintenanceIds=(), REQUEST=None):
        "Delete a Maintenance Window to this device"
        import types
        if type(maintenanceIds) in types.StringTypes:
            maintenanceIds = [maintenanceIds]
        for id in maintenanceIds:
            self.maintenanceWindows._delObject(id)
        self.setLastChange()
        if REQUEST:
            REQUEST['message'] = "Maintenace Window Deleted"
            return self.callZenScreen(REQUEST)
                          
    security.declareProtected('Change Device', 'manage_addAdministrativeRole')
    def manage_addAdministrativeRole(self, newId, REQUEST=None):
        "Add a Admin Role to this device"
        us = self.ZenUsers.getUserSettings(newId)
        if us:
            ar = DeviceAdministrativeRole(newId)
            if us.defaultAdminRole:
                ar.role = us.defaultAdminRole
                ar.level = us.defaultAdminLevel
            self.adminRoles._setObject(newId, ar)
            ar = self.adminRoles._getOb(newId)
            ar.userSetting.addRelation(us)
        if REQUEST:
            REQUEST['message'] = "Administrative Role Added"
            return self.callZenScreen(REQUEST)


    def manage_editAdministrativeRoles(self, ids, role, level, REQUEST=None):
        """Edit list of admin roles.
        """
        if type(ids) in types.StringTypes:
            ids = [ids]
            role = [role]
            level = [level]
        for i, id in enumerate(ids):
            ar = self.adminRoles._getOb(id)
            if ar.role != role[i]: ar.role = role[i]
            if ar.level != level[i]: ar.level = level[i]
        if REQUEST:
            REQUEST['message'] = "Administrative Roles Updated"
            return self.callZenScreen(REQUEST)
        

    security.declareProtected('Change Device','manage_deleteAdministrativeRole')
    def manage_deleteAdministrativeRole(self, delids=(), REQUEST=None):
        "Delete a admin role to this device"
        if type(delids) in types.StringTypes:
            delids = [delids]
        for id in delids:
            self.adminRoles._delObject(id)
        if REQUEST:
            if delids:
                REQUEST['message'] = "Administrative Roles Deleted"
            return self.callZenScreen(REQUEST)
                          

    def monitorDevice(self):
        """Is device production state >= zProdStateThreshold.
        """
        return self.productionState >= self.zProdStateThreshold


    def snmpMonitorDevice(self):
        "Is this device subject to SNMP monitoring?"
        return (self.monitorDevice()
                and not self.zSnmpMonitorIgnore
                and self.zSnmpCommunity)


    def getProductionStateString(self):
        """Return the prodstate as a string.
        """
        return self.convertProdState(self.productionState)

    def getPriorityString(self):
        """Return the device priority as a string.
        """
        return self.convertPriority(self.priority)
        
    def getPingStatusString(self):
        '''Return the pingStatus as a string
        '''
        return self.convertStatus(self.getPingStatus())

    def getSnmpStatusString(self):
        '''Return the snmpStatus as a string
        '''
        return self.convertStatus(self.getSnmpStatus())

    security.declareProtected('Change Device', 'setProdState')
    def setProdState(self, state):
        """Set a device's production state as an integer.
        """
        self.productionState = int(state)
        try:
            zem = self.dmd.ZenEventManager
            try:
                conn = zem.connect()
                curs = conn.cursor()
                curs.execute("update status set prodState=%d where device='%s'" % (
                                self.productionState, self.id))
            finally: zem.close(conn)
        except OperationalError:
            log.exception("failed to update events with new prodState")

    security.declareProtected('Change Device', 'setPriority')
    def setPriority(self, priority):
        """ Set a device's priority as an integer.
        """
        self.priority = int(priority)
        try:
            zem = self.dmd.ZenEventManager
            try:
                conn = zem.connect()
                curs = conn.cursor()
                curs.execute("update status set DevicePriority=%d where device='%s'" % (
                                self.priority, self.id))
            finally: zem.close(conn)
        except OperationalError:
            log.exception("failed to update events with new priority")

    security.declareProtected('Change Device', 'setLastChange')
    def setLastChange(self, value=None):
        """Set the changed datetime for this device. value default is now.
        """
        self._lastChange.setDate(value)


    security.declareProtected('Change Device', 'setSnmpLastCollection')
    def setSnmpLastCollection(self, value=None):
        """Set the last time snmp collection occurred. value default is now.
        """
        self._snmpLastCollection.setDate(value)


    security.declareProtected('Change Device', 'addManufacturer')
    def addManufacturer(self, newHWManufacturerName=None,
                        newSWManufacturerName=None, REQUEST=None):
        """Add a manufacturer to the database"""
        mname = newHWManufacturerName
        field = 'hwManufacturer'
        if not mname:
            mname = newSWManufacturerName
            field = 'osManufacturer'
        self.getDmdRoot("Manufacturers").createManufacturer(mname)
        if REQUEST:
            REQUEST[field] = mname
            REQUEST['message'] = ("Added Manufacturer %s at time:" % mname)
            return self.callZenScreen(REQUEST)




    security.declareProtected('Change Device', 'setHWProduct')
    def setHWProduct(self, newHWProductName=None, hwManufacturer=None, 
                        REQUEST=None):
        """set the productName of this device"""
        added = False
        if newHWProductName and hwManufacturer:
            self.getDmdRoot("Manufacturers").createHardwareProduct(
                                        newHWProductName, hwManufacturer)
            added = True
        if REQUEST:
            if added:
                REQUEST['hwProductName'] = newHWProductName
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setOSProduct')
    def setOSProduct(self, newOSProductName=None, osManufacturer=None, REQUEST=None):
        """set the productName of this device"""
        if newOSProductName:
            self.getDmdRoot("Manufacturers").createSoftwareProduct(
                                        newOSProductName, osManufacturer)
        if REQUEST:
            if newOSProductName:
                REQUEST['osProductName'] = newOSProductName
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setLocation')
    def setLocation(self, locationPath, REQUEST=None):
        """set the location of a device within a generic location path"""
        locobj = self.getDmdRoot("Locations").createOrganizer(locationPath)
        self.addRelation("location", locobj)


    def addLocation(self, newLocationPath, REQUEST=None):
        """Add a new location and relate it to this device"""
        locobj = self.getDmdRoot("Locations").createOrganizer(newLocationPath)
        if REQUEST:
            REQUEST['locationPath'] = newLocationPath
            REQUEST['message'] = "Added Location %s at time:" % newLocationPath
            return self.callZenScreen(REQUEST)
   

    security.declareProtected('Change Device', 'setPerformanceMonitor')
    def setPerformanceMonitor(self, performanceMonitor,
                            newPerformanceMonitor=None, REQUEST=None):
        """set the performance monitor for this device if newPerformanceMonitor
        is passed in create it"""
        if newPerformanceMonitor: performanceMonitor = newPerformanceMonitor
        obj = self.getDmdRoot("Monitors").getPerformanceMonitor(
                                                    performanceMonitor)
        self.addRelation("perfServer", obj)
        if REQUEST:
            REQUEST['message'] = "Set Performance %s at time:" % performanceMonitor
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setStatusMonitors')
    def setStatusMonitors(self, statusMonitors):
        """Set Status Monitor by list statusMonitors
        """
        objGetter = self.getDmdRoot("Monitors").getStatusMonitor
        self._setRelations("monitors", objGetter, statusMonitors)


    security.declareProtected('Change Device', 'addStatusMonitor')
    def addStatusMonitor(self, newStatusMonitor=None, REQUEST=None):
        """add new status monitor to the database and this device"""
        if newStatusMonitor:
            mon = self.getDmdRoot("Monitors").getStatusMonitor(newStatusMonitor)
            self.addRelation("monitors", mon)
        if REQUEST:
            if newStatusMonitor:
                REQUEST['message'] = "Added Monitor %s at time:" % \
                                                    newStatusMonitor
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setGroups')
    def setGroups(self, groupPaths):
        """set the list of groups for this device based on a list of paths"""
        objGetter = self.getDmdRoot("Groups").createOrganizer
        self._setRelations("groups", objGetter, groupPaths)


    security.declareProtected('Change Device', 'addDeviceGroup')
    def addDeviceGroup(self, newDeviceGroupPath, REQUEST=None):
        """add a device group to the database and this device"""
        group = self.getDmdRoot("Groups").createOrganizer(newDeviceGroupPath)
        self.addRelation("groups", group)
        if REQUEST:
            REQUEST['message'] = "Added Group %s at time:" % newDeviceGroupPath
            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setSystems')
    def setSystems(self, systemPaths):
        """set a list of systems to this device using their system paths"""
        objGetter = self.getDmdRoot("Systems").createOrganizer
        self._setRelations("systems", objGetter, systemPaths)
      

    security.declareProtected('Change Device', 'addSystem')
    def addSystem(self, newSystemPath, REQUEST=None):
        """add a systems to this device using its system path"""
        sys = self.getDmdRoot("Systems").createOrganizer(newSystemPath)
        self.addRelation("systems", sys)
        if REQUEST:

            return self.callZenScreen(REQUEST)


    security.declareProtected('Change Device', 'setTerminalServer')
    def setTerminalServer(self, termservername):
        termserver = self.findDevice(termservername)
        if termserver:
            self.addRelation('termserver', termserver)


    def _setRelations(self, relName, objGetter, relPaths):
        """set related objects to this device"""
        if type(relPaths) != type([]) and type(relPaths) != type(()):
            relPaths = [relPaths,]
        relPaths = filter(lambda x: x.strip(), relPaths)
        rel = getattr(self, relName, None)
        if not rel:
            raise AttributeError, "Relation %s not found" % relName
        curRelIds = {}
        for value in rel.objectValuesAll():
            curRelIds[value.getOrganizerName()] = value
        for path in relPaths:
            if not curRelIds.has_key(path):
                robj = objGetter(path)
                self.addRelation(relName, robj)
            else:
                del curRelIds[path]
        for obj in curRelIds.values():
            self.removeRelation(relName, obj)


    def getExpandedLinks(self):
        'Return the expanded zComment property'
        from Products.ZenUtils.ZenTales import talesEval
        try:
            return talesEval('string:' + self.zLinks, self)
        except Exception, ex:
            import cgi
            return "<i class='errortitle'>%s</i>" % cgi.escape(str(ex))

    ####################################################################
    # Private getter functions that implement DeviceResultInt
    ####################################################################

    security.declareProtected('View', 'device')
    def device(self):
        """support DeviceResultInt mixin class"""
        return self


    ####################################################################
    # Status Management Functions used by status monitors
    ####################################################################


    def pastSnmpMaxFailures(self):
        """Device has more SNMP failures than maxFailures on its status mon."""
        statusmon = self.monitors()
        if len(statusmon) > 0:
            statusmon = statusmon[0]
            return statusmon.maxFailures < self.getSnmpStatusNumber()
        return False


    security.declareProtected('Manage Device Status', 'getLastPollSnmpUpTime')
    def getLastPollSnmpUpTime(self):
        """set the value of the snmpUpTime status object"""
        return self._lastPollSnmpUpTime.getStatus()


    security.declareProtected('Manage Device Status', 'setLastPollSnmpUpTime')
    def setLastPollSnmpUpTime(self, value):
        """set the value of the snmpUpTime status object"""
        self._lastPollSnmpUpTime.setStatus(value)


    def snmpAgeCheck(self, hours):
        lastcoll = self.getSnmpLastCollection()
        hours = hours/24.0
        if DateTime() > lastcoll + hours: return 1


    def applyProductContext(self):
        """Apply zProperties inherited from Product Contexts.
        """
        self._applyProdContext(self.hw.getProductContext())
        self._applyProdContext(self.os.getProductContext())
        for soft in self.os.software():
            self._applyProdContext(soft.getProductContext())
        

    def _applyProdContext(self, context):
        """Apply zProperties taken for the product context passed in.
        context is a list of tuples returned from getProductContext
        on a MEProduct.
        """
        for name, value in context:
            if name == "zDeviceClass" and value:
                log.info("move device to %s", value)
                self.moveDevices(value, self.id)
            elif name == "zDeviceGroup" and value:
                log.info("add device to group %s", value)
                self.addDeviceGroup(value)
            elif name == "zSystem" and value:
                log.info("add device to system %s", value)
                self.addSystem(value)



    ####################################################################
    # Management Functions
    ####################################################################

    security.declareProtected('Change Device', 'collectDevice')
    def collectDevice(self, setlog=True, REQUEST=None, generateEvents=False):
        """collect the configuration of this device.
        """
        if REQUEST and setlog:
            response = REQUEST.RESPONSE
            dlh = self.deviceLoggingHeader()
            idx = dlh.rindex("</table>")
            response.write(str(dlh[:idx]))
            handler = setWebLoggingStream(response)
        try:
            from Products.DataCollector.zenmodeler import ZenModeler
            sc = ZenModeler(noopts=1,app=self.getPhysicalRoot(),single=True)
            sc.options.force = True
            sc.generateEvents = generateEvents
            sc.collectSingle(self)
            sc.reactorLoop()
        except:
            log.exception('exception collecting data for device %s',self.id)
            sc.stop()
        else:
            log.info('collected snmp information for device %s',self.id)
                            
        if REQUEST and setlog:
            response.write(self.deviceLoggingFooter())
            clearWebLoggingStream(handler)



    security.declareProtected('Change Device', 'deleteDevice')
    def deleteDevice(self, REQUEST=None):
        """Delete device from the DMD"""
        parent = self.getPrimaryParent()
        self.getEventManager().manage_deleteHeartbeat(self.getId())
        self.getEventManager().manage_deleteAllEvents(self.getId())
        parent._delObject(self.getId())
        if REQUEST:
            REQUEST['RESPONSE'].redirect(parent.absolute_url() +
                                            "/deviceOrganizerStatus")


    security.declareProtected('Change Device', 'renameDevice')
    def renameDevice(self, newId=None, REQUEST=None):
        """Rename device from the DMD"""
        if newId:
            if not isinstance(newId, unicode):
                newId = self.prepId(newId)
            parent = self.getPrimaryParent()
            parent.manage_renameObject(self.getId(), newId)
            self.setLastChange()
        if REQUEST: return self()


    def manage_afterAdd(self, item, container):
        """
        Device only propagates afterAdd if it is the added object.
        """
        super(Device,self).manage_afterAdd(item, container)
        self.index_object()


    def manage_afterClone(self, item):
        """Not really sure when this is called."""
        super(Device,self).manage_afterClone(item)
        self.index_object()


    def manage_beforeDelete(self, item, container):
        """
        Device only propagates beforeDelete if we are being deleted or copied.
        Moving and renaming don't propagate.
        """
        super(Device,self).manage_beforeDelete(item, container)
        self.unindex_object()


    def cacheComponents(self):
        "Read current RRD values for all of a device's components"
        paths = self.getRRDPaths()[:]
        #FIXME need better way to scope and need to get DataSources 
        # from RRDTemplates
        #for c in self.os.interfaces(): paths.extend(c.getRRDPaths())
        for c in self.os.filesystems(): paths.extend(c.getRRDPaths())
        #for c in self.hw.harddisks(): paths.extend(c.getRRDPaths())
        objpaq = self.primaryAq()
        perfServer = objpaq.getPerformanceServer()
        if perfServer:
            import RRDView
            try:
                result = perfServer.currentValues(paths)
                if result:
                    RRDView.updateCache(zip(paths, result))
            except Exception:
                log.exception("Unable to cache values for %s", self.id);


    def getUserCommandTargets(self):
        ''' Called by Commandable.doCommand() to ascertain objects on which
        a UserCommand should be executed.
        '''
        return [self]

    def getUserCommandEnvironment(self):
        environ = Commandable.getUserCommandEnvironment(self)
        context = self.primaryAq()
        environ.update({'dev': context,  'device': context,})
        return environ


InitializeClass(Device)
