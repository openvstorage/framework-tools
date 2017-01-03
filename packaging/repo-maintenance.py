# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Repo maintenance module
"""

import os
from distutils.version import LooseVersion
from optparse import OptionParser
from sourcecollector import SourceCollector

if __name__ == '__main__':
    parser = OptionParser(description='Open vStorage repo maintenance')
    parser.add_option('-f', '--from-release', dest='from_release')
    parser.add_option('-t', '--to-release', dest='to_release')
    parser.add_option('-s', '--skip', dest='skip')
    options, args = parser.parse_args()

    settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))

    package_info = settings['repositories']['packages'].get('debian', [])
    for destination in package_info:
        server = destination['ip']
        user = destination['user']
        base_path = destination['base_path']

        print 'Processing {0}@{1}'.format(user, server)

        from_package_map = {}
        to_package_map = {}

        print '  Reading releases'
        for release, package_map in {options.from_release: from_package_map,
                                     options.to_release: to_package_map}.iteritems():
            print '    {0}'.format(release)

            ls_command = "ssh {0}@{1} 'ls {2}/{3}/*.deb'".format(user, server, base_path, release)
            packages = SourceCollector.run(command=ls_command,
                                           working_directory='/').strip().splitlines()
            for package in packages:
                deb = package.replace('{0}/{1}/'.format(base_path, release), '')
                name, version, _ = deb.split('_', 2)
                if options.skip is not None and name.startswith(options.skip):
                    continue

                if name in package_map:
                    if LooseVersion(version) > LooseVersion(package_map[name][0]):
                        package_map[name] = (version, package, deb)
                else:
                    package_map[name] = (version, package, deb)

        print '  Adding packages'
        for package in from_package_map:
            package_file_path = from_package_map[package][1]
            package_file = from_package_map[package][2]
            add = False
            older = False
            if package in to_package_map:
                if LooseVersion(from_package_map[package][0]) > LooseVersion(to_package_map[package][0]):
                    add = True
                    older = True
            else:
                add = True
            if add is True:
                print '    {0} need to be copied as {1} is newer than {2}'.format(
                    package, from_package_map[package][0], to_package_map.get(package, ['(none)'])[0]
                )
                cp_command = "ssh {0}@{1} 'cp {2} {3}/{4}/'".format(
                    user, server, package_file_path, base_path, options.to_release
                )
                SourceCollector.run(command=cp_command,
                                    working_directory='/')
                destination_path = '{0}/{1}/{2}'.format(base_path, options.to_release, package_file)
                repo_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian includedeb {3} {4}'".format(
                    user, server, base_path, options.to_release, destination_path
                )
                SourceCollector.run(command=repo_command,
                                    working_directory='/')
                if older is True:
                    print '    Removing old package'
                    old_path = '{0}/{1}/{2}'.format(base_path, options.to_release, to_package_map[package][2])
                    rm_command = "ssh {0}@{1} 'rm {4}'".format(
                        user, server, base_path, options.to_release, old_path
                    )
                    SourceCollector.run(command=rm_command,
                                        working_directory='/')
