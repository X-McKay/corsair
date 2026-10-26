module Attachments
  # Read a stored attachment by name under the given root.
  def self.read(root:, name:)
    path = File.expand_path(name, root)
    raise ArgumentError, 'attachment outside storage' unless path.start_with?(root + File::SEPARATOR)
    File.read(path)
  end
end
