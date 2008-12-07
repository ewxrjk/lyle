LYLE_VERSION=0.8+
GPL=/usr/share/common-licenses/GPL

prefix=/usr/local
exec_prefix=${prefix}
bindir=${exec_prefix}/bin

INSTALL=install -c

all:
	perl -wc lyle.cgi
	perl -wc lyle-refresh

install:
	$(INSTALL) -m 555 lyle-refresh $(bindir)/lyle-refresh

dist:
	rm -rf lyle-$(LYLE_VERSION)
	mkdir lyle-$(LYLE_VERSION)
	mkdir lyle-$(LYLE_VERSION)/images
	mkdir lyle-$(LYLE_VERSION)/templates
	mkdir lyle-$(LYLE_VERSION)/ChangeLog.d
	$(INSTALL) -m 755 lyle.cgi lyle-$(LYLE_VERSION)/lyle.cgi
	$(INSTALL) -m 755 lyle-refresh lyle-$(LYLE_VERSION)/lyle-refresh
	$(INSTALL) -m 644 README lyle-$(LYLE_VERSION)/README
	$(INSTALL) -m 644 CHANGES lyle-$(LYLE_VERSION)/CHANGES
	$(INSTALL) -m 644 css.txt lyle-$(LYLE_VERSION)/css.txt
	$(INSTALL) -m 644 $(GPL) lyle-$(LYLE_VERSION)/COPYING
	$(INSTALL) -m 644 images/*.png lyle-$(LYLE_VERSION)/images/.
	$(INSTALL) -m 644 templates/*.tmpl lyle-$(LYLE_VERSION)/templates/.
	$(INSTALL) -m 644 ChangeLog.d/lyle--*[^~] \
		lyle-$(LYLE_VERSION)/ChangeLog.d/.
	tar cf lyle-$(LYLE_VERSION).tar lyle-$(LYLE_VERSION)
	gzip -9f lyle-$(LYLE_VERSION).tar

install-lyle:
	$(INSTALL) -m 755 lyle.cgi $$HOME/public_html/gallery.cgi
	$(INSTALL) -m 755 lyle-refresh $$HOME/bin/.
	$(INSTALL) -m 644 templates/*.tmpl \
		$$HOME/public_html/web/photos/stdtemplates/.
	$(INSTALL) -m 644 images/*.png $$HOME/public_html/web/photos/.
