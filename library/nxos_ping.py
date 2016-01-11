#!/usr/bin/env python

# Copyright 2015 Jason Edelman <jedelman8@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

DOCUMENTATION = '''
---

module: nxos_ping
short_description: Tests reachability using ping from Nexus switch
description:
    - Tests reachability using ping from switch to a remote destination
author: Jason Edelman (@jedelman8)
requirements:
    - NX-API 1.0
    - NX-OS 6.1(2)I3(1)
    - pycsco
    - xmltodict
notes:
    - While username and password are not required params, they are
      if you are not using the .netauth file.  .netauth file is recommended
      as it will clean up the each task in the playbook by not requiring
      the username and password params for every tasks.
    - Using the username and password params will override the .netauth file
options:
    dest:
        description:
            - IP address or hostname (resolvable by switch) of remote node
        required: true
        default: null
        choices: []
        aliases: []
    count:
        description:
            - Number of packets to send
        required: false
        default: 4
        choices: []
        aliases: []
    source:
        description:
            - Source IP Address
        required: false
        default: null
        choices: []
        aliases: []
    vrf:
        description:
            - Outgoing VRF
        required: false
        default: null
        choices: []
        aliases: []
    host:
        description:
            - IP Address or hostname (resolvable by Ansible control host)
              of the target NX-API enabled switch
        required: true
        default: null
        choices: []
        aliases: []
    port:
        description:
            - TCP port to use for communication with switch
        required: false
        default: null
        choices: []
        aliases: []
    username:
        description:
            - Username used to login to the switch
        required: false
        default: null
        choices: []
        aliases: []
    password:
        description:
            - Password used to login to the switch
        required: false
        default: null
        choices: []
        aliases: []
    protocol:
        description:
            - Dictates connection protocol to use for NX-API
        required: false
        default: http
        choices: ['http', 'https']
        aliases: []
'''

EXAMPLES = '''
# test reachability to 8.8.8.8 using mgmt vrf
- nxos_ping: dest=8.8.8.8 vrf=management host={{ inventory_hostname }}

# Test reachability to a few different public IPs using mgmt vrf
- nxos_ping: dest={{ item }} vrf=management host={{ inventory_hostname }}
  with_items:
    - 8.8.8.8
    - 4.4.4.4
    - 198.6.1.4

'''

RETURN = '''
action:
    description:
        - Show what action has been performed
    returned: always
    type: string
    sample: "PING 8.8.8.8 (8.8.8.8): 56 data bytes"
command:
    description: Show the command sent
    returned: always
    type: string
    sample: "ping 8.8.8.8 count 8 vrf management"
count:
    description: Show amount of packets sent
    returned: always
    type: string
    sample: "8"
dest:
    description: Show the ping destination
    returned: always
    type: string
    sample: "8.8.8.8"
rtt:
    description: Show RTT stats
    returned: always
    type: dict
    sample: {"avg": "6.264","max":"6.564",
            "min": "5.978"}
packets_rx:
    description: Packets successfully received
    returned: always
    type: string
    sample: "8"
packets_tx:
    description: Packets successfully transmitted
    returned: always
    type: string
    sample: "8"
packet_loss:
    description: Percentage of packets lost
    returned: always
    type: string
    sample: "0.00%"
'''


import socket
import xmltodict
try:
    HAS_PYCSCO = True
    from pycsco.nxos.device import Device
    from pycsco.nxos.device import Auth
    from pycsco.nxos.error import CLIError
except ImportError as ie:
    HAS_PYCSCO = False


def parsed_data_from_device(device, command, module):
    try:
        data = device.show(command, text=True)
    except CLIError as clie:
        module.fail_json(msg='Error sending {}'.format(command),
                         error=str(clie))
    data_dict = xmltodict.parse(data[1])
    body = data_dict['ins_api']['outputs']['output']['body']
    return body


def get_summary(results_list, reference_point):
    summary_string = results_list[reference_point+1]
    summary_list = summary_string.split(',')
    pkts_tx = summary_list[0].split('packets')[0].strip()
    pkts_rx = summary_list[1].split('packets')[0].strip()
    pkt_loss = summary_list[2].split('packet')[0].strip()
    summary = dict(packets_tx=pkts_tx,
                   packets_rx=pkts_rx,
                   packet_loss=pkt_loss)

    return summary


def get_rtt(results_list, packet_loss, location):
    if packet_loss != '100.00%':
        rtt_string = results_list[location]
        base = rtt_string.split('=')[1]
        rtt_list = base.split('/')
        min_rtt = rtt_list[0].lstrip()
        avg_rtt = rtt_list[1]
        max_rtt = rtt_list[2][:-3]
        rtt = dict(min=min_rtt, avg=avg_rtt, max=max_rtt)
    else:
        rtt = dict(min=None, avg=None, max=None)

    return rtt


def get_statistics_summary_line(response_as_list):
    for each in response_as_list:
        if '---' in each:
            index = response_as_list.index(each)
    return index


def get_ping_results(device, ping_command, module):
    ping = parsed_data_from_device(device, ping_command, module)
    splitted_ping = ping.split('\n')
    reference_point = get_statistics_summary_line(splitted_ping)
    summary = get_summary(splitted_ping, reference_point)
    rtt = get_rtt(splitted_ping, summary['packet_loss'], reference_point+2)

    return (splitted_ping, summary, rtt)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            dest=dict(required=True),
            count=dict(default=4),
            vrf=dict(),
            source=dict(),
            protocol=dict(choices=['http', 'https'], default='http'),
            host=dict(required=True),
            port=dict(required=False, type='int', default=None),
            username=dict(type='str'),
            password=dict(type='str'),
        ),
        supports_check_mode=False
    )
    if not HAS_PYCSCO:
        module.fail_json(msg='There was a problem loading pycsco')

    auth = Auth(vendor='cisco', model='nexus')
    username = module.params['username'] or auth.username
    password = module.params['password'] or auth.password
    protocol = module.params['protocol']
    port = module.params['port']
    host = socket.gethostbyname(module.params['host'])

    destination = module.params['dest']
    count = module.params['count']
    vrf = module.params['vrf']
    source = module.params['source']

    device = Device(ip=host, username=username, password=password,
                    protocol=protocol, port=port)

    OPTIONS = {
        'vrf': vrf,
        'count': count,
        'source': source
        }

    ping_command = 'ping {0}'.format(destination)

    for command, arg in OPTIONS.iteritems():
        if arg:
            ping_command += ' {0} {1}'.format(command, arg)

    ping_results, summary, rtt = get_ping_results(device, ping_command, module)

    packet_loss = summary['packet_loss']
    packets_rx = summary['packets_rx']
    packets_tx = summary['packets_tx']

    results = {}

    results['command'] = ping_command
    results['action'] = ping_results[0]
    results['dest'] = destination
    results['count'] = count
    results['packets_tx'] = packets_tx
    results['packets_rx'] = packets_rx
    results['packet_loss'] = packet_loss
    results['rtt'] = rtt

    module.exit_json(**results)


from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
