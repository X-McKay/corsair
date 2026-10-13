use strict;
use warnings;
use Test::More;
use Responder;

subtest test_control => sub {
    like(Responder::redirect_headers('/home'), qr{\r\nLocation: /home\r\n}, 'a plain location is set');
};

subtest test_security => sub {
    my $headers = Responder::redirect_headers("/home\r\nSet-Cookie: injected=1");
    unlike($headers, qr{\r\nSet-Cookie:}, 'a CRLF in the location adds no header');
};

done_testing;
