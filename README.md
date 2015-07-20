# ncpy

Simple tcp netcat clone in python for use as a ProxyCommand in ssh.

Initial code was taken from http://4thmouse.com/index.php/2008/02/22/netcat-clone-in-three-languages-part-ii-python/

After some testing it resulted to suffer from performance problems related to the handling of stdin so I fixed it.

Now it performs almost on par with regular netcat and replaces it quite well as ssh's helper.
