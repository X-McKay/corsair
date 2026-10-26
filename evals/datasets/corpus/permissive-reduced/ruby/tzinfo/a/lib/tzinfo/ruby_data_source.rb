# Reduced from tzinfo (tzinfo/tzinfo) lib/tzinfo/ruby_data_source.rb:
# TZInfo::RubyDataSource#load_timezone_info validates a timezone identifier and loads the
# matching definition file from the data directory. The data directory is supplied to the
# constructor and the require is performed as upstream so the module runs offline.
module TZInfo
  class InvalidTimezoneIdentifier < StandardError; end

  # A DataSource that loads data from a set of Ruby definition files rooted at a base path.
  class RubyDataSource
    # The base path is supplied directly: it stands in for the upstream constructor that
    # locates the bundled data gem. It performs no loading and decides nothing about the
    # identifier.
    def initialize(base_path)
      @base_path = base_path
    end

    # Returns a TimezoneInfo instance for a given identifier.
    # Raises InvalidTimezoneIdentifier if the timezone is not found or the
    # identifier is invalid.
    def load_timezone_info(identifier)
      raise InvalidTimezoneIdentifier, 'Invalid identifier' if identifier !~ /\A[A-Za-z0-9\+\-_]+(\/[A-Za-z0-9\+\-_]+)*\z/
      
      identifier = identifier.gsub(/-/, '__m__').gsub(/\+/, '__p__')
      
      identifier = identifier.split('/')
      begin
        require_definition(identifier)
        
        m = Data::Definitions
        identifier.each {|part|
          m = m.const_get(part)
        }
        
        m.get
      rescue LoadError, NameError => e
        raise InvalidTimezoneIdentifier, e.message
      end
    end

    private

    # Requires a zone definition by its identifier (split on /).
    def require_definition(identifier)
      require_data(*(['definitions'] + identifier))
    end

    # Requires a file from the data directory.
    def require_data(*file)
      require(File.join(@base_path, *file))
    end
  end
end
