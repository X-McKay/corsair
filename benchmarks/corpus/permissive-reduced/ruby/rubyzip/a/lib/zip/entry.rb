# Reduced from rubyzip (rubyzip/rubyzip) lib/zip/entry.rb: Zip::Entry name handling and
# extraction. The archive read/decompress collaborator is replaced by a plain in-memory write
# so the module runs offline.
require 'pathname'
require 'fileutils'

module Zip
  class Entry
    attr_accessor :name

    def initialize(name, content = '')
      @name = name
      @content = content
    end

    def valid_entry_name?
      cleanpath = Pathname.new(@name).cleanpath
      return false unless cleanpath.relative?

      root = ::File::SEPARATOR
      naive_expanded_path = ::File.join(root, cleanpath.to_s)
      cleanpath.expand_path(root).to_s == naive_expanded_path
    end

    def extract(dest_dir)
      return nil unless valid_entry_name?

      target = ::File.join(dest_dir, @name)
      ::FileUtils.mkdir_p(::File.dirname(target))
      ::File.write(target, @content)
      target
    end
  end
end
