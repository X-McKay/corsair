module Attachments
  ROOT = File.expand_path('../storage', __dir__)

  # Read a stored attachment by name.
  def self.read(name)
    path = File.expand_path(name, ROOT)
    raise ArgumentError, 'attachment outside storage' unless path.start_with?(ROOT + File::SEPARATOR)
    File.read(path)
  end
end
