import setuptools

setuptools.setup(
    name="kubessh",
    version='0.1',
    url="https://github.com/yuvipanda/kubessh",
    author="Yuvi Panda",
    author_email="yuvipanda@gmail.com",
    license="Apache-2",
    description="SSH server to spawn users into kubernetes pods",
    packages=setuptools.find_packages(),
    install_requires=[
        'kubernetes==5.*',
        'asyncssh==1.12.*',
        'ptyprocess==0.5.*',
        'escapism'
    ],
    entry_points = {
        'console_scripts': [
            'kubessh=kubessh.server:main'
        ]
    }
)
