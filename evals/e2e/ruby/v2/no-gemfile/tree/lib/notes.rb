module Notes
  # Print a note file through the system pager.
  def self.show(name)
    system("cat notes/#{name}")
  end
end
