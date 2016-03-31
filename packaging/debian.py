# Copyright 2016 iNuron NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Debian packager module
"""
import os
import shutil
from sourcecollector import SourceCollector


class DebianPackager(object):
    """
    DebianPackager class

    Responsible for creating debian packages from the source archive
    """

    def __init__(self):
        """
        Dummy init method, DebianPackager is static
        """
        raise NotImplementedError('DebianPackager is a static class')

    @staticmethod
    def package(metadata):
        """
        Packages a given package.
        """

        product, release, version_string, revision_date, package_name = metadata

        settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
        working_directory = settings['base_path'].format(product)
        repo_path_code = SourceCollector.repo_path_code.format(working_directory)
        package_path = SourceCollector.package_path.format(working_directory)

        # Prepare
        # /<pp>/debian
        debian_folder = '{0}/debian'.format(package_path)
        if os.path.exists(debian_folder):
            shutil.rmtree(debian_folder)
        # /<rp>/packaging/debian -> /<pp>/debian
        shutil.copytree('{0}/packaging/debian'.format(repo_path_code), debian_folder)

        # Rename tgz
        # /<pp>/<packagename>_1.2.3.tar.gz -> /<pp>/debian/<packagename>_1.2.3.orig.tar.gz
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(package_path, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(debian_folder, package_name, version_string))
        # /<pp>/debian/<packagename>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=debian_folder)

        # Move the debian package metadata into the extracted source
        # /<pp>/debian/debian -> /<pp>/debian/<packagename>-1.2.3/
        SourceCollector.run(command='mv {0}/debian {0}/{1}-{2}/'.format(debian_folder, package_name, version_string),
                            working_directory=package_path)

        # Build changelog entry
        with open('{0}/{1}-{2}/debian/changelog'.format(debian_folder, package_name, version_string), 'w') as changelog_file:
            changelog_file.write("""{0} ({1}-1) {2}; urgency=low

  * For changes, see individual changelogs

 -- Packaging System <engineering@openvstorage.com>  {3}
""".format(package_name, version_string, release, revision_date.strftime('%a, %d %b %Y %H:%M:%S +0000')))

        # Some more tweaks
        SourceCollector.run(command='chmod 770 {0}/{1}-{2}/debian/rules'.format(debian_folder, package_name, version_string),
                            working_directory=package_path)
        SourceCollector.run(command="sed -i -e 's/__NEW_VERSION__/{0}/' *.*".format(version_string),
                            working_directory='{0}/{1}-{2}/debian'.format(debian_folder, package_name, version_string))

        # Build the package
        SourceCollector.run(command='dpkg-buildpackage',
                            working_directory='{0}/{1}-{2}'.format(debian_folder, package_name, version_string))

    @staticmethod
    def upload(metadata):
        """
        Uploads a given set of packages
        """

        product, release, version_string, revision_date, package_name = metadata

        settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
        working_directory = settings['base_path'].format(product)
        package_path = SourceCollector.package_path.format(working_directory)

        package_info = settings['repositories']['packages']['debian']
        server = package_info['ip']
        user = package_info['user']
        base_path = package_info['base_path']
        upload_path = os.path.join(base_path, release)

        print("Uploading {0} {1}".format(package_name, version_string))
        debs_path = os.path.join(package_path, 'debian')
        deb_packages = [filename for filename in os.listdir(debs_path) if filename.endswith('.deb')]

        create_releasename_command = "ssh {0}@{1} mkdir -p {2}".format(user, server, upload_path)
        SourceCollector.run(command=create_releasename_command,
                            working_directory=debs_path)

        for deb_package in deb_packages:
            source_path = os.path.join(debs_path, deb_package)
            destination_path = os.path.join(upload_path, deb_package)

            check_package_command = "ssh {0}@{1} ls {2}".format(user, server, upload_path)
            existing_packages = SourceCollector.run(command=check_package_command,
                                                    working_directory=debs_path).split()
            upload = deb_package not in existing_packages
            if upload is False:
                print("Package already uploaded, done...")
            else:
                scp_command = "scp {0} {1}@{2}:{3}".format(source_path, user, server, destination_path)
                SourceCollector.run(command=scp_command,
                                    working_directory=debs_path)
                remote_command = "ssh {0}@{1} reprepro -Vb {2}/debian includedeb {3} {4}".format(user, server, base_path, release, destination_path)
                SourceCollector.run(command=remote_command,
                                    working_directory=debs_path)
