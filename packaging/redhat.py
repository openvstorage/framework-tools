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

    def __init__(self):
        """
        Dummy init method, RPMPackager is static
        """
        raise NotImplementedError('RPMPackager is a static class')

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
        redhat_folder = '{0}/redhat'.format(package_path)
        if os.path.exists(redhat_folder):
            shutil.rmtree(redhat_folder)
        os.mkdir(redhat_folder)

        # extract tar.gz to redhat_folder
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(package_path, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(redhat_folder, package_name, version_string))
        # /<pp>/debian/<packagename>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=redhat_folder)
        code_source_path = '{0}/{1}-{2}'.format(redhat_folder, package_name, version_string)

        # copy packaging
        source_packaging_path = os.path.join(repo_path_code, 'packaging')
        dest_packaging_path = os.path.join(code_source_path, 'packaging')
        if os.path.exists(source_packaging_path):
            shutil.copytree(source_packaging_path, dest_packaging_path)

        # load config
        config_dir = '{0}/packaging/redhat/cfgs'.format(repo_path_code)
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

            package_root_path = os.path.join(package_path, package_name)
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
                                working_directory=redhat_folder)
            print(os.listdir(redhat_folder))

    @staticmethod
    def upload(metadata):
        """
        Uploads a given set of packages
        """
        product, release, version_string, revision_date, package_name = metadata

        settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
        working_directory = settings['base_path'].format(product)
        package_path = SourceCollector.package_path.format(working_directory)
        redhat_folder = '{0}/redhat'.format(package_path)

        package_info = settings['repositories']['packages']['redhat']
        for destination in package_info:
            server = destination['ip']
            user = destination['user']
            base_path = destination['base_path']

            packages = [p for p in os.listdir(redhat_folder) if p.endswith('.rpm')]
            for package in packages:
                package_source_path = os.path.join(redhat_folder, package)

                command = 'scp {0} {1}@{2}:{3}/pool/{4}'.format(package_source_path, user, server, base_path, release)
                print('Uploading package {0}'.format(package))
                SourceCollector.run(command,
                                    working_directory=redhat_folder)
            if len(packages) > 0:
                # Cleanup existing files
                command = 'ssh {0}@{1} {2}/cleanup_repo.py {2}/pool/{3}/'.format(user, server, base_path, release)
                print(SourceCollector.run(command,
                                          working_directory=redhat_folder))
                command = 'ssh {0}@{1} createrepo --update {2}/dists/{3}'.format(user, server, base_path, release)
                SourceCollector.run(command,
                                    working_directory=redhat_folder)
