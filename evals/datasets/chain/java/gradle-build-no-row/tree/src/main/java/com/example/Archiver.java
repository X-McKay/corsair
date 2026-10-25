package com.example;

public class Archiver {
    /** Compress one directory into a tarball. */
    public Process compress(String directory) throws Exception {
        return Runtime.getRuntime().exec(new String[]{"sh", "-c", "tar -czf out.tgz " + directory});
    }
}
