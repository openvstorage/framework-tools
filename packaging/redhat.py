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
RPM packager module
"""
import os
import shutil
from ConfigParser import RawConfigParser
from sourcecollector import SourceCollector


class RPMPackager(object):
    """
    RPMPackager class

    Responsible for creating rpm packages from the source archive
    """

    def __init__(self, source_collector, dry_run=False):
        """
        Creates an instance of a DebianPacker
        This instance is tied to a SourceCollector instance which holds all product information
        :param source_collector: SourceCollector instance
        :param dry_run: Run the source collector in dry run mode
        * This will not do any impacting changes (like uploading/tagging)
        """
        self.source_collector = source_collector
        self.dry_run = dry_run

        self.redhat_folder = '{0}/redhat'.format(self.source_collector.path_package)

        # Milestone
        self.packaged = False

    def package(self):
        """
        Packages a given package.
        """
        # Validation
        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        version_string = self.source_collector.release_repo
        revision_date = self.source_collector.revision_date
        package_name = self.source_collector.package_name
        package_tags = self.source_collector.tags
        if any(item is None for item in [product, release_repo, version_string, revision_date, package_name, package_tags]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        path_code = self.source_collector.path_code
        path_package = self.source_collector.path_package

        # Prepare
        if os.path.exists(self.redhat_folder):
            shutil.rmtree(self.redhat_folder)
        os.mkdir(self.redhat_folder)

        # Extract tar.gz to redhat_folder
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(path_package, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(self.redhat_folder, package_name, version_string))
        # /<pp>/debian/<packagename>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=self.redhat_folder)
        code_source_path = '{0}/{1}-{2}'.format(self.redhat_folder, package_name, version_string)

        # copy packaging
        source_packaging_path = os.path.join(path_code, 'packaging')
        dest_packaging_path = os.path.join(code_source_path, 'packaging')
        if os.path.exists(source_packaging_path):
            shutil.copytree(source_packaging_path, dest_packaging_path)

        # load config
        config_dir = '{0}/packaging/redhat/cfgs'.format(path_code)
        packages = os.listdir(config_dir)
        for package in packages:
            package_filename = '{0}/{1}'.format(config_dir, package)
            package_cfg = RawConfigParser()
            package_cfg.read(package_filename)

            package_name = package_cfg.get('main', 'name')
            dirs = package_cfg.get('main', 'dirs')
            files = package_cfg.get('main', 'files')
            depends_packages = package_cfg.get('main', 'depends').replace('$Version', version_string.replace('-', '_'))

            depends = ""
            if depends_packages != '':
                depends = []
                for depends_package in depends_packages.split(','):
                    depends.append('-d "{0}"'.format(depends_package.strip()))
                depends = ' '.join(depends)

            package_root_path = os.path.join(path_package, package_name)
            if os.path.exists(package_root_path):
                shutil.rmtree(package_root_path)
            os.mkdir(package_root_path)

            for dir_ in dirs.split(','):
                dir_ = dir_.strip()
                if dir_ != "''":
                    source_dir, dest_location = dir_.split('=')
                    # source_dir = dir to copy - from repo root
                    # dest_location = dir under which to copy the source_dir
                    source_full_path = os.path.join(code_source_path, source_dir.strip())
                    dest_full_path = os.path.join(package_root_path, dest_location.strip())
                    shutil.copytree(source_full_path, dest_full_path)
            for file_ in files.split(','):
                file_ = file_.strip()
                if file_ != "''" and file_ != '':
                    source_file, dest_location = file_.split('=')
                    source_full_path = os.path.join(code_source_path, source_file.strip())
                    dest_full_path = os.path.join(package_root_path, dest_location.strip())

                    if not os.path.exists(dest_full_path):
                        os.makedirs(dest_full_path)
                    shutil.copy(source_full_path, dest_full_path)
            before_install, after_install = ' ', ' '
            script_root = '{0}/packaging/redhat/scripts'.format(code_source_path)
            before_install_script = '{0}.before-install.sh'.format(package_name)
            before_install_script_path = os.path.join(script_root, before_install_script)
            if os.path.exists(before_install_script_path):
                before_install = ' --before-install {0} '.format(before_install_script_path)
            after_install_script = '{0}.after-install.sh'.format(package_name)
            after_install_script_path = os.path.join(script_root, after_install_script)
            if os.path.exists(after_install_script_path):
                after_install = ' --after-install {0} '.format(after_install_script_path)
                SourceCollector.run(command="sed -i -e 's/$Version/{0}/g' {1}".format(version_string,
                                                                                      after_install_script_path),
                                    working_directory='{0}'.format(script_root))

            params = {'version': version_string,
                      'package_name': package_cfg.get('main', 'name'),
                      'summary': package_cfg.get('main', 'summary'),
                      'license': package_cfg.get('main', 'license'),
                      'URL': package_cfg.get('main', 'URL'),
                      'source': package_cfg.get('main', 'source'),
                      'arch': package_cfg.get('main', 'arch'),
                      'description': package_cfg.get('main', 'description'),
                      'maintainer': package_cfg.get('main', 'maintainer'),
                      'depends': depends,
                      'package_root': package_root_path,
                      'before_install': before_install,
                      'after_install': after_install,
            }

            command = """fpm -s dir -t rpm -n {package_name} -v {version} --description "{description}" --maintainer "{maintainer}" --license "{license}" --url {URL} -a {arch} --vendor "Open vStorage" {depends}{before_install}{after_install} --prefix=/ -C {package_root}""".format(**params)

            SourceCollector.run(command,
                                working_directory=self.redhat_folder)
            print(os.listdir(self.redhat_folder))
            self.packaged = True

    def upload(self):
        """
        Uploads a given set of packages
        """
        # Validation
        if self.packaged is False:
            raise RuntimeError('Product has not yet been packaged. Unable to upload it')

        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        version_string = self.source_collector.release_repo
        revision_date = self.source_collector.revision_date
        package_name = self.source_collector.package_name
        package_tags = self.source_collector.tags
        if any(item is None for item in [product, release_repo, version_string, revision_date, package_name, package_tags]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        settings = self.source_collector.settings
        package_info = settings['repositories']['packages'].get('redhat', [])
        for destination in package_info:
            server = destination['ip']
            tags = destination.get('tags', [])
            if len(set(tags).intersection(package_tags)) == 0:
                print 'Skipping {0} ({1}). {2} requested'.format(server, tags, package_tags)
                continue
            user = destination['user']
            base_path = destination['base_path']

            packages = [p for p in os.listdir(self.redhat_folder) if p.endswith('.rpm')]
            for package in packages:
                package_source_path = os.path.join(self.redhat_folder, package)

                command = 'scp {0} {1}@{2}:{3}/pool/{4}'.format(package_source_path, user, server, base_path, release_repo)
                print('Uploading package {0}'.format(package))
                SourceCollector.run(command=command,
                                    working_directory=self.redhat_folder,
                                    print_only=self.dry_run)
            if len(packages) > 0:
                # Cleanup existing files
                command = 'ssh {0}@{1} {2}/cleanup_repo.py {2}/pool/{3}/'.format(user, server, base_path, release_repo)
                print(SourceCollector.run(command=command,
                                          working_directory=self.redhat_folder,
                                          print_only=self.dry_run))
                command = 'ssh {0}@{1} createrepo --update {2}/dists/{3}'.format(user, server, base_path, release_repo)
                SourceCollector.run(command=command,
                                    working_directory=self.redhat_folder,
                                    print_only=self.dry_run)
