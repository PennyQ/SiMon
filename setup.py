from setuptools import setup, find_packages

# name is the package name in pip, should be lower case and not conflict with existing packages
# packages are code source

setup(name='astrosimon',
      version='0.1.0',
      description='A simulation monitor for astrophysical N-body simulations',
      url='https://github.com/maxwelltsai/SiMon',
      author='Maxwell Cai, Penny Qian',
      author_email='pennyqxr@gmail.com',
      license='',
      packages=find_packages(),
      zip_safe=False,
      install_requires=['python-daemon'],
      entry_points = {
      'console_scripts': 
      ['simon = SiMon.simon:main'],
      },
      )