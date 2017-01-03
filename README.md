# Open vStorage - Framework tools

The ```framework-tools``` repository contains tools used when working on the Open vStorage product.

## Packaging

The packaging folder contains all logic to create packages (at this moment debian and redhat packages) for all the Open vStorage Framework repositories.

Usage:

```
$ ./packager.py -p <product> -r <release> [-e <revision>][--no-rpm] [--no-deb]
```

Where:

* *product*: The product name that needs to be packaged. Using ```settings.json``` it refers to a repository that will be packaged
* *release*: The name of the release to be packaged. Using ```settings.json``` it refers to a branch on the repository, as in the Open vStorage repositories, every release has its own branch. Using the ```branch_map``` data in the settings file, the branchname-releasename mapping can be altered.
* *revision*: To build a specific revision. If this parameter is given, the ```release``` parameter must be ```experimental```.
* The ```--no-rpm``` and ```--no-deb``` prevent these package formats from being generated. If both are passed, only the source archive will be generated.
