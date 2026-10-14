require "uri"

module Rack
  PATH_INFO = "PATH_INFO"

  module Utils
    PATH_SEPS = Regexp.union(*[::File::SEPARATOR, ::File::ALT_SEPARATOR].compact)
    URI_PARSER = defined?(::URI::RFC2396_PARSER) ? ::URI::RFC2396_PARSER : ::URI::DEFAULT_PARSER

    def self.unescape_path(s)
      URI_PARSER.unescape s
    end

    def self.clean_path_info(path_info)
      parts = path_info.split PATH_SEPS

      clean = []

      parts.each do |part|
        next if part.empty? || part == "."
        part == ".." ? clean.pop : clean << part
      end

      clean_path = clean.join(::File::SEPARATOR)
      clean_path.prepend("/") if parts.empty? || parts.first.empty?
      clean_path
    end
  end

  # Reads a file located under +root+ for the request path and returns its
  # contents, or a 404 response when no such file exists.
  class FileReader
    def initialize(root)
      @root = root
    end

    def call(env)
      full = ::File.join(@root, env[PATH_INFO])
      if ::File.file?(full)
        [200, { "content-type" => "text/plain" }, [::File.read(full)]]
      else
        [404, {}, []]
      end
    end
  end

  class Static
    def initialize(app, options = {})
      @app = app
      @urls = options[:urls] || ["/favicon.ico"]
      @index = options[:index]
      root = options[:root] || Dir.pwd
      @file_server = FileReader.new(root)
    end

    def add_index_root?(path)
      @index && route_file(path) && path.end_with?("/")
    end

    def overwrite_file_path(path)
      @urls.kind_of?(Hash) && @urls.key?(path) || add_index_root?(path)
    end

    def route_file(path)
      @urls.kind_of?(Array) && @urls.any? { |url| path.index(url) == 0 }
    end

    def can_serve(path)
      route_file(path) || overwrite_file_path(path)
    end

    def call(env)
      path = env[PATH_INFO]
      target = Utils.clean_path_info(Utils.unescape_path(path))

      if can_serve(target)
        @file_server.call(env)
      else
        @app.call(env)
      end
    end
  end
end
