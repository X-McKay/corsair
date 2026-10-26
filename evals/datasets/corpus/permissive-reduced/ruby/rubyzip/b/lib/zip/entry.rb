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

    def extract(dest_dir)
      target = ::File.join(dest_dir, @name)
      ::FileUtils.mkdir_p(::File.dirname(target))
      ::File.write(target, @content)
      target
    end
  end
end
