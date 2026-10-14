# Reduced from ruby-git (ruby-git/ruby-git) lib/git/lib.rb: Git::Lib#ls_files parses the output
# of the git ls-files subcommand into a hash keyed by path. The method that would spawn the git
# process is replaced by a recorder that returns canned output so the module runs offline.
require 'git/escaped_path'

module Git
  class Lib
    def ls_files(location=nil)
      location ||= '.'
      hsh = {}
      command_lines('ls-files', '--stage', location).each do |line|
        (info, file) = line.split("\t")
        (mode, sha, stage) = info.split
        if file.start_with?('"') && file.end_with?('"')
          file = Git::EscapedPath.new(file[1..-2]).unescape
        end
        hsh[file] = {:path => file, :mode_index => mode, :sha_index => sha, :stage => stage}
      end
      hsh
    end

    # Stands in for the method that spawns the git process: it returns the canned lines it is
    # given and performs no execution. It decides nothing about their content.
    def command_lines(cmd, *opts)
      @recorded_argv = [cmd] + opts
      @canned_lines || []
    end

    attr_reader :recorded_argv
    attr_writer :canned_lines
  end
end
