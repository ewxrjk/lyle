#! /usr/bin/perl -w
#
# Copyright (C) 2003, 2004, 2005, 2008 Richard Kettlewell
# Copyright (C) 2004 Ross Younger
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
#

#
# possible query strings:
#
#  ?dir=DIR                         display an index for DIR
#  ?dir=DIR&display=PIC             html-wrapped display of PIC
#  ?dir=DIR&pic=PIC&scale=FACTOR    scaled+rotated display of PIC
#  ?dir=DIR&pic=PIC&w=WIDTH&h=HEIGHT  scaled+rotated display of PIC
#  ?dir=DIR&pic=PIC                 raw data of PIC
#  ?dir=DIR&exif=PIC                run jhead on PIC
#

use strict;
use vars qw(@dirs %caption $rootdir $thumbnail $lyleurl $title $description
	    $displaysize %prev %next %w %h @pics %rotate $lock $index
	    $cachedir $cacheurl $rooturl %crop $imagesurl
	    $maxdisplaywidth $maxdisplayheight
	    $maxthumbwidth $maxthumbheight $jpegquality
	    @templates %comments @autodirs);
use IO::File;
use Errno;
use Fcntl ':flock';
use Digest::MD5 qw(md5_hex);
use Image::Magick;
use POSIX;

sub invalid($$);
sub urlquote($);
sub file_more_recent($$);
sub htmlquote($);
sub tag($@);
sub mkdir_if_not_exist($);
sub writefile($@);
sub get_cached_info($);
sub print_array(\@);
sub print_hash(\%);
sub perlquote($);
sub imgurl($$$);
sub size($$$$);
sub width($$);
sub height($$);
sub displayurl($$);
sub exifurl($$);
sub take_lock();
sub release_lock();
sub transform_image($$$$);
sub dosubst($$);
sub validate_filename($);

our $error_guard = 0;

my @pw = getpwuid($<);
my $home = $pw[7];
my $conf = "$home/.lyle.conf";
$lock = "$home/.lyle.lock";
@dirs = ();
@autodirs = ();
$thumbnail = 0;
$displaysize = 0;
%rotate = ();
%crop = ();
%comments = ();
$maxdisplaywidth = 640;
$maxdisplayheight = 512;
$maxthumbwidth = 128;
$maxthumbheight = 96;
# imagemagick default jpegquality is 75

# parse CGI args
my %args = map(
	       do {
		 s/\+/ /g;
		 s/%([0-9a-fA-F]{2})/chr(hex($1))/ge;
		 $_;
	       }, split /[\&=]/, $ENV{'QUERY_STRING'});

# read configuration
eval {
  (do $conf)
    || error("error reading $conf: $!\n", "", "500 internal error");
};
if($@) {
  error($@);
}

# check configuration makes sense
error("\$rootdir not set", "", "500 internal error") unless defined $rootdir;
error("\$rooturl not set", "", "500 internal error") unless defined $rooturl;
error("\$cachedir not set", "", "500 internal error") unless defined $cachedir;
error("\$cacheurl not set", "", "500 internal error") unless defined $cacheurl;
error("\$lyleurl not set", "", "500 internal error") unless defined $lyleurl;
error("\@dirs not set", "", "500 internal error") unless @dirs or @autodirs;
error("\@templates not set", "", "500 internal error") unless @templates;

# check that we want a valid directory
my $dir;
if(exists $args{'dir'}) {
  $dir = $args{'dir'};
} elsif(exists $ENV{'PATH_INFO'}) {
  ($dir = $ENV{'PATH_INFO'}) =~ s/\A\/+//; # strip leading slashes
} else {
  error("directory not set and no PATH_INFO", "", "404 not found");
}
my %dirs = map(($_ => 1), @dirs);
# Add subdirectories of anything in autodirs
for my $ad (@autodirs) {
    my $d = POSIX::opendir("$rootdir/$ad");
    if(!defined $d) {
	print STDERR "opening $ad: $!\n";
	next;
    }
    my @f = POSIX::readdir($d);
    for my $f (sort(@f)) {
	my $d = "$ad/$f";
	if(!exists $dirs{$d} and -e "$rootdir/$d/info.pl") {
	    push(@dirs, $d);
	    $dirs{$d} = 1;	# keep up to date
	}
    }
}
invalid("directory", $dir) if !exists $dirs{$dir};
my $info = "$rootdir/$dir/info.pl";
if(-e $info) {
  (do $info)
    || error("error reading $info: $!\n", "", "500 missing info.pl");
}

get_cached_info($dir);

if(exists $args{'pic'}) {
  # redirect to a possibly scaled version of the picture
  my $pic = $args{'pic'};
  validate_filename($pic);
  if(exists $args{'scale'}) {
    my $scale = $args{'scale'};
    invalid("scale", $scale) if($scale !~ /^[0-9]+(\.[0-9]+)?$/
				|| $scale > 1
				|| $scale < 0.001);
    my $url = transform_image($dir, $pic, $scale, 1);
    output("Location: $url\n\n");
  } elsif(exists $args{'w'} && exists $args{'h'}) {
    my ($w, $h) = ($args{'w'}, $args{'h'});
    invalid("width", $w) if($w !~ /^[0-9]+$/
			    || $w <= 0 || $w > 2048);
    invalid("height", $h) if($h !~ /^[0-9]+$/
			     || $h <= 0 || $h > 2048);
    my $url = transform_image($dir, $pic, [$w, $h], 1);
    output("Location: $url\n\n");
  } else {
    output("Location: $rooturl/$dir/$pic\n\n");
  }
} else {
  my @nav = ();
  my @image = ();
  my @thumbnails = ();
  my $pagetitle;
  my $template;
  my $comment;
  if(exists $args{'display'}) {
    # display one pic
    $template = "picture.tmpl";
    my $pic = $args{'display'};
    validate_filename($pic);
    if(-e "$rootdir/$dir/$pic") {
      my ($w, $h, $link);
      ($w, $h) = size($pic, $displaysize,
		      $maxdisplaywidth, $maxdisplayheight);
      push(@image, tag("a",
		       "href" => galleryurl(dir => $dir,
					    pic => $pic)),
	   tag("img",
	       "src" => galleryurl(dir => $dir,
				   pic => $pic,
				   w => $w,
				   h => $h),
	       "class" => "galleryDisplay",
	       "alt" => $title,
	       "width" => $w, "height" => $h),
	   "</a>");
      
    } else {
      push(@image, "Picture not available");
    }
    $pagetitle = (exists $caption{$pic} && $caption{$pic} ne ""
		  ? $caption{$pic}
		  : $pic);
    if(exists $prev{$pic}) {
	push(@nav, join("",
			tag("a", "href" => displayurl($dir, $prev{$pic})),
			tag("img", "src" => "$imagesurl/left.png",
			    "class" => "galleryIcon",
			    "border" => 0,
			    "alt" => $prev{$pic},
			    "title" => $prev{$pic}),
			"</a>\n"));
    } else {
	push(@nav, tag("img", "src" => "$imagesurl/blank.png",
		       "class" => "galleryIcon",
		       "border" => 0,
		       "alt" => ""));
    }
    push(@nav, join("",
		    tag("a", "href" => galleryurl(dir => $dir)),
		    tag("img", "src" => "$imagesurl/up.png",
			"class" => "galleryIcon",
		"border" => 0,
			"alt" => "index",
			"title" => "index"),
		    "</a>\n"));
    if(exists $next{$pic}) {
	push(@nav, join("",
			tag("a", "href" => displayurl($dir, $next{$pic})),
			tag("img", "src" => "$imagesurl/right.png",
			    "class" => "galleryIcon",
			    "border" => 0,
			    "alt" => $next{$pic},
			    "title" => $next{$pic}),
			"</a>\n"));
    } else {
	push(@nav, tag("img", "src" => "$imagesurl/blank.png",
		       "class" => "galleryIcon",
		       "border" => 0,
		       "alt" => ""));
    }
    push(@nav, join("",
		    tag("a", "href" => exifurl($dir, $pic)),
		    tag("img", "src" => "$imagesurl/data.png",
			"class" => "galleryIcon",
			"border" => 0,
			"alt" => "EXIF",
			"title" => "EXIF"),
		    "</a>\n"));
    $comment = $comments{$pic};
  } elsif(exists $args{'exif'}) {
    # dump exif data
    my $pic = $args{'exif'};
    validate_filename($pic);
    if(-e "$rootdir/$dir/$pic") {
      output("Content-Type: text/plain\n\n");
      system("jhead", "$rootdir/$dir/$pic");
    } else {
      error("No such file", "No such file as $dir/$pic", 404);
    }
    exit(0);
  } else {
    # display an index of all the pics
    $template = "index.tmpl";
    $pagetitle = $title;
    # build prev/next arrays
    my (%nextdir, %prevdir);
    for my $n (0 .. $#dirs) {
      $nextdir{$dirs[$n]} = $dirs[$n + 1] if $n < $#dirs;
      $prevdir{$dirs[$n]} = $dirs[$n - 1] if $n > 0;
    }
    if(exists $prevdir{$dir}) {
      push(@nav,
	   tag("a", "href" => galleryurl(dir => $prevdir{$dir})),
	   tag("img", "src" => "$imagesurl/left.png",
	       "class" => "galleryIcon",
	       "border" => 0,
	       "alt" => "previous",
	       "title" => "previous"),
	   "</a>\n");
    } else {
	push(@nav, tag("img", "src" => "$imagesurl/blank.png",
		       "class" => "galleryIcon",
		       "border" => 0,
		       "alt" => ""));
    }
    if(defined $index) {
      push(@nav,
	   tag("a", "href" => $index),
	   tag("img", "src" => "$imagesurl/up.png",
	       "class" => "galleryIcon",
	       "border" => 0,
	       "alt" => "more galleries",
	       "title" => "more galleries"),
	   "</a>\n");
    }
    if(exists $nextdir{$dir}) {
      push(@nav,
	   tag("a", "href" => galleryurl(dir => $nextdir{$dir})),
	   tag("img", "src" => "$imagesurl/right.png",
	       "class" => "galleryIcon",
	       "border" => 0,
	       "alt" => "next",
	       "title" => "next"),
	   "</a>\n");
    } else {
	push(@nav, tag("img", "src" => "$imagesurl/blank.png",
		       "class" => "galleryIcon",
		       "border" => 0,
		       "alt" => ""));
    }
  }
  for my $pic (@pics) {
    my ($w, $h) = size($pic, $thumbnail,
		       $maxthumbwidth, $maxthumbheight);
    push(@thumbnails,
	 tag("a", "name" => $pic), "</a>".
	 tag("a",
	     "href" => displayurl($dir, $pic)),
	 tag("img",
	     "class" => "galleryThumbnail",
	     "src" => transform_image($dir, $pic, [$w, $h], 0),
	     "width" => $w,
	     "height" => $h,
	     "alt" => "",
	     (exists $caption{$pic}
	      ? ("title" => $caption{$pic})
	      : ())),
	 "</a>\n");
  }
  output("Content-Type: text/html\n\n",
	 dosubst($template,
		 {
		  generated => "<!-- generated " . localtime() . " -->",
		  title => htmlquote($pagetitle),
		  navigation => join("", @nav),
		  thumbnails => join("", @thumbnails),
		  image => join("", @image),
		  description => $description || '',
		  comment => $comment || '',
		 }));
}

# Generate an error page and terminate
#
# Usage: error(OPTIONAL-ERROR, OPTIONAL-TEXT, OPTIONAL-CODE)
#  ERROR is the summary
#  TEXT is the detail
#  CODE is the HTTP response code
sub error {
  my $error = shift || "";
  my $text = shift || "";
  my $code = shift || "";

  if($error_guard++) {
    die "$0: recursive error: $error, $text\n";
  }

  print STDERR "lyle.cgi: ERROR: $error\n";
  print STDERR "----\n$text\n----\n" if defined $text;

  output("Content-Type: text/html\n",
	 $code ne "" ? "Status: $code\n" : "",
	 "\n",
	 dosubst("error.tmpl",,
		 {
		  generated => "<!-- generated " . localtime() . " -->",
		  error => htmlquote($error),
		  detail => htmlquote($text),
		 }));
  exit 0;
}

# HTML-quote its argument
sub htmlquote($) {
  local $_ = shift;

  s/[^\ a-zA-Z0-9:\.\-\%\/~\?\=_]/sprintf("&\#%d;", ord($&))/ge;
  return $_;
}

# URL-quote its argument
sub urlquote($) {
  local $_ = shift;

  s/[^a-zA-Z0-9:\.\-\/_]/sprintf("%%%02X", ord($&))/ge;
  return $_;
}

# Write arguments to STDOUT with error checking
sub output {
  (print STDOUT @_) || die "$0: stdout: $!\n";
}

# Compare modification times of two files
#
# Usage: file_more_recent(PATH-1, PATH-2)
# Returns: true iff mtime(PATH-1) >= mtime(PATH-2)
sub file_more_recent($$) {
  my ($a, $b) = @_;

  my @a = stat $a;
  my @b = stat $b;
  return $a[9] >= $b[9];
}

# Compare two filenames, for use by sort
sub cmpname {
  if($a =~ /\A(\d+)(.*)/) {
    my ($an, $at) = ($1, $2);
    if($b =~ /\A(\d+)(.*)/) {
      my ($bn, $bt) = ($1, $2);
      if($an < $bn) {
	return -1;
      } elsif($an > $bn) {
	return 1;
      }
    }
  }
  return $a cmp $b;
}

# Report a type mismatch and terminate.
#
# Usage: invalid(KIND, WHAT)
#
# Reports that WHAT is not a valid KIND.
sub invalid($$) {
  my ($kind, $what) = @_;

  $what =~ s/\\/\\\\/g;
  $what =~ s/[\0-\37\177\200-\237\377]/sprintf("\\%03o", ord($&))/ge;
  error("invalid $kind", "$what is not a valid $kind.", "404 Not found");
}

# Construct an HTML attribute.
#
# Usage: attribute(NAME, VALUE)
# Returns: NAME="VALUE", HTML-quoted.
sub attribute($$) {
  my ($key, $value) = @_;
  return "$key=\"" . htmlquote($value) . "\"";
}

# Construct an HTML open tag
#
# Usage: tag(ELEMENT-NAME, NAME-1 => VALUE-1, NAME-2 => VALUE-2, ...)
sub tag($@) {
  my $tag = shift;
  my @r = ();
  while(@_ > 0) {
    my $k = shift;
    my $v = shift;
    push(@r, attribute($k, $v));
  }
  return "<" . join(" ", $tag, @r) . ">";
}

# Make a directory if it does not exist already.
sub mkdir_if_not_exist($) {
  my $path = shift;
  mkdir($path, 0755) || do {
    error("error creating $path: $!", "", "500 internal error")
      if $! != Errno::EEXIST;
  };
}

# Write out a file safely.
sub writefile($@) {
  my $path = shift;
  my $tmp = "$path.$$.tmp";
  open(OUTPUT, ">$tmp") || error("error creating $tmp: $!", "", "500 internal error");
  (print OUTPUT @_) || error("error writing to $tmp: $!", "", "500 internal error");
  (close OUTPUT) || error("error closing $tmp: $!", "", "500 internal error");
  (rename $tmp, $path) || error("error renaming $tmp to $path: $!", "", "500 internal error");
}

# Return true if the cache is up to date.
sub cache_up_to_date($$) {
  my ($dir, $cache) = @_;

  if(-e $cache) {
    my @c = stat _ ;
    my @d = stat $dir or error("cannot stat $dir: $!", "", "500 internal error");
    return 0 if $c[9] <= $d[9];
    @d = stat "$dir/info.pl" or error("cannot stat $dir/info.pl: $!", "", "500 internal error");
    return 0 if $c[9] <= $d[9];
    return 1;
  }
  return 0;
}

# Load the cache.
sub get_cached_info($) {
  my $dir = shift;
  my $hash = md5_hex("$rootdir/$dir cache");
  my $cache ="$cachedir/$hash.cache";
  local $_;

  if(cache_up_to_date("$rootdir/$dir", $cache)) {
    (do $cache)
      || error("error reading $cache: $!\n", "", "500 internal error");
  } else {
    take_lock();
    if(cache_up_to_date("$rootdir/$dir", $cache)) {
      release_lock();
      (do $cache)
	|| error("error reading $cache: $!\n", "", "500 internal error");
      return;
    }
    # get list of pictures
    opendir(DIR, "$rootdir/$dir");
    @pics = sort cmpname grep { /\.(jpe?g|png)\z/i } readdir DIR;
    closedir DIR;
    # build prev/next arrays
    for my $n (0 .. $#pics) {
      $next{$pics[$n]} = $pics[$n + 1] if $n < $#pics;
      $prev{$pics[$n]} = $pics[$n - 1] if $n > 0;
    }
    # build size arrays
    my $image = Image::Magick->new();
    for my $pic (@pics) {
      my ($w, $h, $s, $f) = $image->Ping("$rootdir/$dir/$pic");
      if(defined $w && defined $h) {
	($w{$pic}, $h{$pic}) = ($w, $h);
      }
    }
    writefile($cache,
	      "\@pics = ", print_array(@pics), ";\n",
	      "\%next = ", print_hash(%next), ";\n",
	      "\%prev = ", print_hash(%prev), ";\n",
	      "\%w = ", print_hash(%w), ";\n",
	      "\%h = ", print_hash(%h), ";\n",
	      "1;\n");
    release_lock();
  }
}

sub print_array(\@) {
  my $a = shift;
  return ("(\n",
	  map("  " . perlquote($_) . ",\n", @$a),
	  ")");
}

sub print_hash(\%) {
  my $h = shift;
  return ("(\n",
	  map("  " . perlquote($_) . " => " . perlquote($h->{$_}) . ",\n",
	      sort keys %$h),
	  ")");
}

# Quote for Perl.
sub perlquote($) {
  local $_ = shift;
  s/\"\\/\\$&/g;
  return "\"$_\"";
}

# Construct a display URL
#
# Usage: displayurl(DIR, PIC)
# Returns: the URL of the display page for DIR/PIC
sub displayurl($$) {
  my ($dir, $pic) = @_;

  return galleryurl(dir => $dir,
		    display => $pic) . "#$pic";
}

# Construct an EXIF URL
#
# Usage: exifurl(DIR, PIC)
# Returns: the URL of the EXIF data for DIR/PIC
sub exifurl($$) {
  my ($dir, $pic) = @_;

  return galleryurl(dir => $dir,
		    exif => $pic);
}

# Construct a generic lyle url
#
# Usage: galleryurl(NAME-1 => VALUE-1, NAME-2 => VALUE-2, ...)
# Returns: the Lyle URL with the given parameters.
sub galleryurl {
  my $url;
  my %a = @_;
  if($lyleurl =~ /\/$/) {
    if(exists $a{dir}) {
      $url = "$lyleurl" . urlquote($a{dir});
    } else {
      $url = $lyleurl;
    }
    delete $a{dir};
  } else {
    $url = "$lyleurl";
  }
  local $_;
  return "$url?" . join("&",
			map(urlquote($_)."=".urlquote($a{$_}),
			    sort keys %a));
}

# Transform an image
#
# Usage: transform_image(DIR, PIC, SCALE, LOCK)
# Returns: the URL of the cached form of the image.
#
# SCALE is as for size() below.  LOCK is nonzero to take the lock while
# doing the transformation.
sub transform_image($$$$) {
  my ($dir, $pic, $scale, $lock) = @_;
  my ($w, $h) = size($pic, $scale, 0, 0);
  my $ext;
  my $path = "$dir/$pic";
  my $geo = "${w}x${h}";
  my $name = "$rootdir/$dir/$pic geo:$geo";
  $name .= " rotate:$rotate{$pic}" if exists $rotate{$pic};
  $name .= " crop:$crop{$pic}" if exists $crop{$pic};
  $name .= " quality:$jpegquality" if defined $jpegquality;
  if($pic =~ /\.([a-zA-Z0-9]+)$/) {
    $ext = lc $1;
    if($ext eq 'jpg') {
      $ext = 'jpeg';
    }
  } else {
    error("cannot deduce file type for $pic", "", "500 internal error");
  }
  if($ext eq 'jpeg') {
      # vary hash to keep up with bug fix
      $name .= " jpegtran:-copy_all";
  }
  my $hash = md5_hex($name);
  my $scaled = "$cachedir/$hash.$ext";
  my $tmp = "$cachedir/tmp$$.$hash.$ext";
  if(!-e $scaled) {
    # possibly take the lock to reduce concurrency (not to
    # *guarantee* serialization)
    take_lock() if $lock;
    my $image = Image::Magick->new();
    my $e;
    ($e = $image->Read("$rootdir/$path")) and error("reading $rootdir/$path: $e");
    $image->Set(quality=>$jpegquality) if defined $jpegquality;
    $image->Crop($crop{$pic}) if exists $crop{$pic};
    $image->Rotate($rotate{$pic}) if exists $rotate{$pic};
    $image->Scale($geo);
    my $output;
    if($ext eq 'jpeg') {
      $output = new IO::File("|jpegtran -copy all -optimize > \Q$tmp\E")
	or error("error invoking jpegtran: $!");
    } else {
      $output = new IO::File($tmp, "w")
	or error("error opening $tmp: $!");
    }
    ($e = $image->Write(file => $output, filename=>$tmp))
	and error("writing $tmp: $e");
    $output->close() or error("error closing output (wstat:$?/errno:$!)");
    (rename $tmp, $scaled)
      || error("error renaming $tmp to $scaled: $!");
    release_lock() if $lock;
  }
  return "$cacheurl/$hash.$ext";
}

# Compute the size of an image
#
# Usage: size(PIC, SCALE, MAX-WIDTH, MAX-HEIGHT)
# Returns: (WIDTH,HEIGHT)
#
# If SCALE is an array ref then it contains a width and a height
# Else if SCALE > 1.0 then it is a target width
# Else it is actually a scale.
# If the chosen scale makes the image bigger than MAX-WIDTH/HEIGHT then it
# is scaled down to fit.
# The return value is the actual dimensions and scale chosen.
sub size($$$$) {
  my ($pic, $scale, $mw, $mh) = @_;

  my ($w, $h) = ($w{$pic}, $h{$pic});
  # rotate
  ($w, $h) = ($h, $w) if $rotate{$pic};
  # default scale
  if(ref $scale eq 'ARRAY') {
      my $newscale = $scale->[0] / $w;
      ($w, $h) = @$scale;
      $scale = $newscale;
  } else {
      $scale = 1.0 if ! $scale;
      # scales bigger than 1.0 are widths
      if($scale > 1.0) {
	  $scale = $scale / $w;
      }
      # apply scale
      $w *= $scale; $h *= $scale;
  }
  # apply width/height limits
  if($mw && $w > $mw) {
    my $rescale = $mw / $w;
    $scale *= $rescale;
    $w *= $rescale; $h *= $rescale;
  }
  if($mh && $h > $mh) {
    my $rescale = $mh / $h;
    $scale *= $rescale;
    $w *= $rescale; $h *= $rescale;
  }
  # only clamp to integer on return
  return (int($w), int($h));
}

sub take_lock() {
  if(defined $lock) {
    open(LOCKFILE, ">>$lock") || error("error opening $lock: $!\n");
    flock(LOCKFILE, LOCK_EX) || error("error locking $lock: $!\n");
  }
}

sub release_lock() {
  close LOCKFILE;
}

sub validate_filename($) {
  my $pic = shift;
  invalid("filename", $pic) if $pic !~ /\A[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+\z/;
}

sub expand($$) {
  my ($key, $expansions) = @_;
  my $param;
  if($key =~ /:/) {
    ($key, $param) = ($`, $');	#'
  } else {
    $param = "";
  }
  error("\@$key\@ does not exist\n") if ! exists $expansions->{$key};
  error("\@$key\@ not defined\n") if ! defined $expansions->{$key};
  my $expansion = $expansions->{$key};
  if(ref $expansion) {
    if(ref $expansion eq 'CODE') {
      return join("", &$expansion($param,$expansions));
    } else {
      error "cannot expand $expansion\n";
    }
  } else {
    return $expansion;
  }
}

sub dosubst($$) {
  my ($template, $expansions) = @_;
  my @output = ();
  my $fh;
  for my $dir (@templates) {
    if(-e "$dir/$template") {
      $fh = new IO::File("$dir/$template", "r")
	or error "error opening $dir/$template: $!\n";
      last;
    }
  }
  error "cannot find $template\n" unless defined $fh;
  $expansions->{include} = sub { return dosubst($_[0], $_[1]); };
  while(defined($_ = $fh->getline())) {
    s/@([a-zA-Z]+(:[^@]*)?)@/expand($1, $expansions)/ge;
    push(@output, $_);
  }
  error "error reading $template: $!\n" if $fh->error();
  return @output;
}


END {
  (close STDOUT) || die "$0: stdout: $!\n";
}
