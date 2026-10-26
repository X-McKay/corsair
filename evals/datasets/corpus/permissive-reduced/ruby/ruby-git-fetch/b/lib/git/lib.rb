# Reduced from ruby-git (ruby-git/ruby-git) lib/git/lib.rb: Git::Lib#fetch builds the
# argument list for the git fetch subcommand. The method that would spawn the git process
# is replaced by a recorder that captures the argument list so the module runs offline.
module Git
  class Lib
    def fetch(remote, opts)
      arr_opts = []
      arr_opts << '--tags' if opts[:t] || opts[:tags]
      arr_opts << '--prune' if opts[:p] || opts[:prune]
      arr_opts << '--unshallow' if opts[:unshallow]
      arr_opts << '--depth' << opts[:depth] if opts[:depth]
      arr_opts << '--'
      arr_opts << remote
      arr_opts << opts[:ref] if opts[:ref]

      command('fetch', arr_opts)
    end

    # Stands in for the method that spawns the git process: it records the argument
    # list it is given and performs no execution. It decides nothing about the content.
    def command(cmd, *opts)
      @recorded_argv = [cmd] + opts.flatten
    end

    attr_reader :recorded_argv
  end
end
