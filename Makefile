LYLE_VERSION=0.9+
GPL=/usr/share/common-licenses/GPL

prefix=/usr/local
exec_prefix=${prefix}
bindir=${exec_prefix}/bin

INSTALL=install -c
MKDIR=mkdir

all:
	perl -wc lyle.cgi
	perl -wc lyle-refresh

install:
	$(MKDIR) -m 755 -p $(bindir)
	$(INSTALL) -m 555 lyle-refresh $(bindir)/lyle-refresh

# Build a distributable tarball
dist:
	rm -rf lyle-$(LYLE_VERSION)
	mkdir lyle-$(LYLE_VERSION)
	mkdir lyle-$(LYLE_VERSION)/images
	mkdir lyle-$(LYLE_VERSION)/templates
	$(INSTALL) -m 755 Makefile lyle-$(LYLE_VERSION)/Makefile
	$(INSTALL) -m 755 lyle.cgi lyle-$(LYLE_VERSION)/lyle.cgi
	$(INSTALL) -m 755 lyle-refresh lyle-$(LYLE_VERSION)/lyle-refresh
	$(INSTALL) -m 644 README lyle-$(LYLE_VERSION)/README
	$(INSTALL) -m 644 CHANGES.html lyle-$(LYLE_VERSION)/CHANGES.html
	$(INSTALL) -m 644 css.txt lyle-$(LYLE_VERSION)/css.txt
	$(INSTALL) -m 644 $(GPL) lyle-$(LYLE_VERSION)/COPYING
	$(INSTALL) -m 644 images/*.png lyle-$(LYLE_VERSION)/images/.
	$(INSTALL) -m 644 templates/*.tmpl lyle-$(LYLE_VERSION)/templates/.
	$(INSTALL) -m 644 changelog.arch lyle-$(LYLE_VERSION)/changelog.arch
	bzr log > lyle-$(LYLE_VERSION)/changelog || \
		$(INSTALL) -m 644 changelog lyle-$(LYLE_VERSION)/changelog
	tar cf lyle-$(LYLE_VERSION).tar lyle-$(LYLE_VERSION)
	gzip -9f lyle-$(LYLE_VERSION).tar
	rm -rf lyle-$(LYLE_VERSION)

# Check that the distributable tarball meets the following criteria:
# - it re-dists to itself
# - 'make' works
# - 'make install' works
# - 'make install-lyle' works TODO not done yet!
distcheck:
	$(MAKE) dist
	rm -rf lyle-$(LYLE_VERSION)  lyle-$(LYLE_VERSION).main
	gzip -cd lyle-$(LYLE_VERSION).tar.gz | tar xf -
	mv lyle-$(LYLE_VERSION) lyle-$(LYLE_VERSION).main
	cd lyle-$(LYLE_VERSION).main && $(MAKE) dist
	gzip -cd lyle-$(LYLE_VERSION).main/lyle-$(LYLE_VERSION).tar.gz | tar xf -
	rm -f lyle-$(LYLE_VERSION).main/lyle-$(LYLE_VERSION).tar.gz
	diff -ruN lyle-$(LYLE_VERSION).main lyle-$(LYLE_VERSION)
	cd lyle-$(LYLE_VERSION) && $(MAKE) prefix=`pwd`/_inst
	cd lyle-$(LYLE_VERSION) && $(MAKE) prefix=`pwd`/_inst install
	cd lyle-$(LYLE_VERSION)/_inst && find . -print
	rm -rf lyle-$(LYLE_VERSION).main lyle-$(LYLE_VERSION)

install-lyle:
	$(INSTALL) -m 755 lyle.cgi $$HOME/public_html/gallery.cgi
	$(INSTALL) -m 755 lyle-refresh $$HOME/bin/.
	$(INSTALL) -m 644 templates/*.tmpl \
		$$HOME/public_html/web/photos/stdtemplates/.
	$(INSTALL) -m 644 images/*.png $$HOME/public_html/web/photos/.
