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

        print '  Reading releases'

        source_package_map = {}
        destination_package_map = {}
        for release, package_map in {options.from_release: source_package_map,
                                     options.to_release: destination_package_map}.iteritems():
            print '    {0} repo'.format(release)

            repo_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian list {3}'".format(
                user, server, base_path, release
            )
            packages = SourceCollector.run(command=repo_command,
                                           working_directory='/').strip().splitlines()
            for package in packages:
                _, name, version = package.split(' ')
                if options.skip is not None:
                    should_skip = False
                    skips = options.skip.split(',')
                    for skip in skips:
                        if name.startswith(options.skip):
                            should_skip = True
                            break
                    if should_skip is True:
                        continue

                if name in package_map:
                    if LooseVersion(version) > LooseVersion(package_map[name][0]):
                        package_map[name] = version
                else:
                    package_map[name] = version

        package_map = {}
        for release in [options.from_release, options.to_release, 'upstream']:
            print '    package folder for {0}'.format(release)

            ls_command = "ssh {0}@{1} 'ls {2}/{3}/*.*deb'".format(user, server, base_path, release)
            packages = SourceCollector.run(command=ls_command,
                                           working_directory='/').strip().splitlines()
            for package in packages:
                deb = package.replace('{0}/{1}/'.format(base_path, release), '')
                if '_' not in deb and release == 'upstream':
                    continue  # Unparsable upstream packages
                name, version, _ = deb.split('_', 2)
                if options.skip is not None:
                    should_skip = False
                    skips = options.skip.split(',')
                    for skip in skips:
                        if name.startswith(options.skip):
                            should_skip = True
                            break
                    if should_skip is True:
                        continue

                if name in package_map:
                    if LooseVersion(version) > LooseVersion(package_map[name][0]):
                        package_map[name] = (version, package)
                else:
                    package_map[name] = (version, package)

        print '  Adding packages'
        for package in source_package_map:
            source_version = source_package_map[package]
            destination_version = destination_package_map.get(package)
            if destination_version is None or LooseVersion(source_version) > LooseVersion(destination_version):
                deb_version, deb_location = package_map.get(package, (None, None))
                if deb_location is not None and deb_location.endswith('.ddeb'):
                    continue  # We don't care about debug packages
                print '    {0} need to be copied as {1} is newer than {2}'.format(
                    package, source_version, '(none)' if destination_version is None else destination_version
                )
                if deb_version is None or deb_version != source_version:
                    print '        Warning: Could not locate the deb-file. Please update it manually.'.format(
                        package, source_version
                    )
                    continue

                repo_command = "ssh {0}@{1} 'reprepro -Vb {2}/debian includedeb {3} {4}'".format(
                    user, server, base_path, options.to_release, deb_location
                )
                SourceCollector.run(command=repo_command,
                                    working_directory='/')
