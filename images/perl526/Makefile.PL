use strict;
use warnings;
use ExtUtils::MakeMaker;

WriteMakefile(
    NAME             => 'Corsair::Native',
    VERSION_FROM     => 'lib/Corsair/Native.pm',
    MIN_PERL_VERSION => '5.026',
    TEST_REQUIRES    => { 'Test::More' => '0.88' },
    test             => { TESTS => 't/*.t' },
);
