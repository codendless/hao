#!/usr/bin/env python
"""
Github: https://github.com/whereismyjetpack/pyvmomi-community-samples
Clone a VM from template example
"""
from pyVmomi import vim
from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect
from pyVmomi import vmodl
import atexit
import argparse
import getpass
import ssl
import time
import sys

reload(sys)
sys.setdefaultencoding('utf-8')


def get_args():
    """ Get arguments from CLI """
    parser = argparse.ArgumentParser(
        description='Arguments for talking to vCenter')

    parser.add_argument('-s', '--host',
                        required=True,
                        action='store',
                        help='vSpehre service to connect to')

    parser.add_argument('-o', '--port',
                        type=int,
                        default=443,
                        action='store',
                        help='Port to connect on')

    parser.add_argument('-u', '--user',
                        required=True,
                        action='store',
                        help='Username to use')

    parser.add_argument('-p', '--password',
                        required=False,
                        action='store',
                        help='Password to use')
    
    parser.add_argument('-S', '--disable_ssl_verification',
                        required=False,
                        action='store_true',
                        help='Disable ssl host certificate verification')

    parser.add_argument('-v', '--vm-name',
                        required=True,
                        action='store',
                        help='Name of the VM you wish to make')

    parser.add_argument('--template',
                        required=True,
                        action='store',
                        help='Name of the template/VM \
                            you are cloning from')

    parser.add_argument('--datacenter-name',
                        required=False,
                        action='store',
                        default=None,
                        help='Name of the Datacenter you\
                            wish to use. If omitted, the first\
                            datacenter will be used.')

    parser.add_argument('--vm-folder',
                        required=False,
                        action='store',
                        default=None,
                        help='Name of the VMFolder you wish\
                            the VM to be dumped in. If left blank\
                            The datacenter VM folder will be used')

    parser.add_argument('--datastore-name',
                        required=False,
                        action='store',
                        default=None,
                        help='Datastore you wish the VM to end up on\
                            If left blank, VM will be put on the same \
                            datastore as the template')

    parser.add_argument('--datastorecluster-name',
                        required=False,
                        action='store',
                        default=None,
                        help='Datastorecluster (DRS Storagepod) you wish the VM to end up on \
                             Will override the datastore-name parameter.')

    parser.add_argument('--cluster-name',
                        required=False,
                        action='store',
                        default=None,
                        help='Name of the cluster you wish the VM to\
                            end up on. If left blank the first cluster found\
                            will be used')

    parser.add_argument('--resource-pool',
                        required=False,
                        action='store',
                        default=None,
                        help='Resource Pool to use. If left blank the first\
                            resource pool found will be used')

    parser.add_argument('--host-name',
                        required=False,
                        action='store',
                        default=None,
                        help='Compute node to use. If left blank, a resource from a pool\
                            found will be used')

    parser.add_argument('--power-on',
                        dest='power_on',
                        required=False,
                        action='store_true',
                        help='power on the VM after creation')

    parser.add_argument('--no-power-on',
                        dest='power_on',
                        required=False,
                        action='store_false',
                        help='do not power on the VM after creation')

    parser.add_argument('--disk-type',
                        required=False,
                        action='store',
                        default='thick',
                        choices=['thick', 'thin'],
                        help='thick or thin')

    parser.add_argument('--disk-size',
                        required=False,
                        action='store',
                        help='disk size, in GB, to add to the VM')

    parser.add_argument('--cpus',
                        required=False,
                        action='store',
                        help='Number of virtual processors in a virtual machine')

    parser.add_argument('--memory',
                        required=False,
                        action='store',
                        help='Size of a virtual machine\'s memory, in GB')

    parser.add_argument('--port-group',
                        required=False,
                        action='store',
                        help='port group to connect on')

    parser.add_argument('--ip',
                        required=False,
                        action='store',
                        help='Static ip address')

    parser.add_argument('--gateway',
                        required=False,
                        action='store',
                        help='Gateway')

    parser.add_argument('--mask',
                        required=False,
                        action='store',
                        help='Subnet mask')

    parser.add_argument('--hostname',
                        required=False,
                        action='store',
                        help='Linux hostname')

    parser.set_defaults(power_on=False)

    args = parser.parse_args()

    if not args.password:
        args.password = getpass.getpass(
            prompt='Enter password')

    return args


def wait_for_task(task):
    """ wait for a vCenxter task to finish """
    task_done = False
    while not task_done:
        if task.info.state == 'success':
            return task.info.result

        if task.info.state == 'error':
            raise Exception(task.info.error.msg)
            task_done = True


def get_obj(content, vimtype, name):
    """
    Return an object by name, if name is None the
    first found object is returned
    """
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if name:
            if c.name == name:
                obj = c
                break
        else:
            obj = c
            break

    return obj


def get_nic_obj(content, vimtype, name):
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    for c in container.view:
        if c.name == name:
            obj = c
            break
    return obj


def clone_vm(
        content, template, vm_name,
        datacenter_name, vm_folder, datastore_name,
        cluster_name, resource_pool, host_name, power_on, datastorecluster_name):
    """
    Clone a VM from a template/VM, datacenter_name, vm_folder, datastore_name
    cluster_name, resource_pool, and power_on are all optional.
    """

    # if none git the first one
    datacenter = get_obj(content, [vim.Datacenter], datacenter_name)

    if vm_folder:
        destfolder = get_obj(content, [vim.Folder], vm_folder)
    else:
        destfolder = datacenter.vmFolder

    # if None, get the first one
    cluster = get_obj(content, [vim.ClusterComputeResource], cluster_name)
    computer = get_obj(content, [vim.ComputeResource], host_name)


    if host_name:
        host = get_obj(content, [vim.HostSystem], host_name)
    else:
        host_list = cluster.host
        for host in host_list:
            host_list.sort(
                key=lambda x: x.summary.quickStats.overallMemoryUsage)
        host = host_list[0]

    if datastore_name:
        datastore = get_obj(content, [vim.Datastore], datastore_name)
    else:
        if len(host.datastore) > 1:
            datastore = get_obj(
            content, [vim.Datastore], host.datastore[1].info.name)
        else:
            datastore = get_obj(
            content, [vim.Datastore], host.datastore[0].info.name)

    if resource_pool:
        resource_pool = get_obj(content, [vim.ResourcePool], resource_pool)
    else:
        if host_name:
            resource_pool = computer.resourcePool
        else:
            resource_pool = cluster.resourcePool

    configspec = vim.vm.ConfigSpec()

    if datastorecluster_name:
        podsel = vim.storageDrs.PodSelectionSpec()
        pod = get_obj(content, [vim.StoragePod], datastorecluster_name)
        podsel.storagePod = pod

        storagespec = vim.storageDrs.StoragePlacementSpec()
        storagespec.podSelectionSpec = podsel
        storagespec.type = 'create'
        storagespec.folder = destfolder
        storagespec.resourcePool = resource_pool
        storagespec.configSpec = configspec

        try:
            rec = content.storageResourceManager.RecommendDatastores(
                storageSpec=storagespec)
            rec_action = rec.recommendations[0].action[0]
            real_datastore_name = rec_action.destination.name
        except:
            real_datastore_name = template.datastore[0].info.name

        datastore = get_obj(content, [vim.Datastore], real_datastore_name)

    # set relospec
    relospec = vim.vm.RelocateSpec()
    relospec.datastore = datastore
    relospec.pool = resource_pool
    relospec.host = host

    # set clonespec
    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec
    # clonespec.config = configspec
    # clonespec.customization = customspec
    clonespec.powerOn = power_on
    clonespec.template = False  # Whether the new vm is a template or not.

    task = template.Clone(folder=destfolder, name=vm_name, spec=clonespec)
    wait_for_task(task)


def reconfig_nic(content, template, vm, port_group, cpus, memory):
    """
    :param si: Service Instance
    :param vm: Virtual Machine Object
    :param network: Virtual Network
    """
    spec = vim.vm.ConfigSpec()

    if cpus > 0:
        spec.numCPUs = int(cpus)
    if memory > 0:
        spec.memoryMB = int(memory) * 1024
    spec.cpuHotAddEnabled = True
    spec.memoryHotAddEnabled = True

    nic_changes = []

    nic_spec = vim.vm.device.VirtualDeviceSpec()
    nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit

    nic_spec.device = vim.vm.device.VirtualVmxnet3()

    nic_spec.device.deviceInfo = vim.Description()
    nic_spec.device.deviceInfo.summary = 'vCenter API'

    nic_spec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
    nic_spec.device.backing.useAutoDetect = False
    nic_spec.device.backing.network = get_nic_obj(
        content, [vim.Network], port_group)
    nic_spec.device.backing.deviceName = port_group

    nic_spec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    nic_spec.device.connectable.startConnected = True
    nic_spec.device.connectable.allowGuestControl = True
    nic_spec.device.connectable.connected = True
    nic_spec.device.connectable.status = 'untried'
    nic_spec.device.wakeOnLanEnabled = True
    nic_spec.device.addressType = 'assigned'
    nic_spec.device.key = 4000

    nic_changes.append(nic_spec)
    spec.deviceChange = nic_changes

    e = vm.ReconfigVM_Task(spec=spec)
    wait_for_task(e)


def customize_network(content, vm, ip, gateway, mask, hostname):
    # test
    dns = "192.168.1.1"

    # IP settings
    adaptermap = vim.vm.customization.AdapterMapping()
    adaptermap.adapter = vim.vm.customization.IPSettings()
    adaptermap.adapter.ip = vim.vm.customization.FixedIp()
    adaptermap.adapter.ip.ipAddress = str(ip)
    adaptermap.adapter.gateway = str(gateway)
    adaptermap.adapter.subnetMask = str(mask)
    # adaptermap.adapter.primaryWINS = str(ip) 

    # DNS settings
    globalip = vim.vm.customization.GlobalIPSettings()
    globalip.dnsServerList = dns

    # Hostname settings (Linux)
    ident = vim.vm.customization.LinuxPrep()
    ident.hostName = vim.vm.customization.FixedName()
    ident.hostName.name = hostname
    # ident = vim.vm.customization.Sysprep()


    # set customspecs
    customspec = vim.vm.customization.Specification()
    customspec.nicSettingMap = [adaptermap]
    customspec.globalIPSettings = globalip
    customspec.identity = ident

    task = vm.Customize(spec=customspec)
    wait_for_task(task)


def add_disk(content, vm, disk_size, disk_type):
    spec = vim.vm.ConfigSpec()
    # get all disks on a VM, set unit_number to the next available
    unit_number = 0
    for dev in vm.config.hardware.device:
        if hasattr(dev.backing, 'fileName'):
            unit_number = int(dev.unitNumber) + 1
            # unit_number 7 reserved for scsi controller
            if unit_number == 7:
                unit_number += 1
            if unit_number >= 16:
                raise Exception("we don't support this many disks")
        if isinstance(dev, vim.vm.device.VirtualSCSIController):
            controller = dev
    # add disk here
    dev_changes = []
    new_disk_kb = int(disk_size) * 1024 * 1024
    disk_spec = vim.vm.device.VirtualDeviceSpec()
    disk_spec.fileOperation = "create"
    disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    disk_spec.device = vim.vm.device.VirtualDisk()
    disk_spec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
    if disk_type == 'thin':
        disk_spec.device.backing.thinProvisioned = True
    disk_spec.device.backing.diskMode = 'persistent'
    disk_spec.device.unitNumber = unit_number
    disk_spec.device.capacityInKB = new_disk_kb
    disk_spec.device.controllerKey = controller.key
    dev_changes.append(disk_spec)
    spec.deviceChange = dev_changes
    e = vm.ReconfigVM_Task(spec=spec)
    wait_for_task(e)

def power_on(vm):
    task = vm.PowerOn()
    wait_for_task(task)


def get_info(vm):
    # summary = vm.summary
    # if summary.guest is not None:
    #     ip_address = summary.guest.ipAddress
    vm = vm.summary.vm
    return vm


def main():
    """
    Let this thing fly
    """
    args = get_args()

    try:
        # connect this thing
        if args.disable_ssl_verification:
            si = SmartConnectNoSSL(host=args.host, 
                                   user=args.user,
                                   pwd=args.password,
                                   port=int(args.port))
        else:
            context = None
            if hasattr(ssl, '_create_unverified_context'):
                context = ssl._create_unverified_context()
            si = SmartConnect(host=args.host,
                              user=args.user,
                              pwd=args.password,
                              port=int(args.port),
                              sslContext=context)
        # disconnect this thing
        atexit.register(Disconnect, si)
        content = si.RetrieveContent()

        # clone
        template = None
        template = get_obj(content, [vim.VirtualMachine], args.template)
        if not template:
            raise Exception("template not found")
            
        clone_vm(
            content, template, args.vm_name,
            args.datacenter_name, args.vm_folder,
            args.datastore_name, args.cluster_name,
            args.resource_pool, args.host_name, args.power_on,
            args.datastorecluster_name)

        # automation configuration
        vm = None
        vm = get_nic_obj(content, [vim.VirtualMachine], args.vm_name)

        if not vm:
            raise Exception("VM not found")
        reconfig_nic(content, template, vm, args.port_group, args.cpus, args.memory)
        # add disk
        if args.disk_size > 0:
            add_disk(content, vm, args.disk_size, args.disk_type)
        customize_network(content, vm, args.ip, args.gateway, args.mask, args.hostname)
        power_on(vm)
        time.sleep(10)
        info = get_info(vm)

    except Exception as e:
        print(str(e))
        sys.exit(-1)

    print (info)    


# start this thing
if __name__ == "__main__":
    main()
