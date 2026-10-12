/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.wiki;

import net.sourceforge.stripes.mock.MockHttpServletRequest;
import net.sourceforge.stripes.mock.MockHttpServletResponse;
import net.sourceforge.stripes.mock.MockServletConfig;
import net.sourceforge.stripes.mock.MockServletContext;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

/** Observes the real servlet's dispatcher choice; a mock dispatcher executes no target. */
public class BenchmarkWikiServletForwardingTest {

    private String forwardFor(final String pathInfo) throws Exception {
        final MockHttpServletRequest request =
                new MockHttpServletRequest("/JSPWiki", "/wiki" + pathInfo);
        request.setPathInfo(pathInfo);
        Assertions.assertEquals(pathInfo, request.getPathInfo(), "request setup must retain path info");
        final MockHttpServletResponse response = new MockHttpServletResponse();
        final MockServletConfig config = new MockServletConfig();
        config.setServletContext(new MockServletContext("/JSPWiki"));
        final WikiServlet servlet = new WikiServlet();
        servlet.init(config);
        try {
            servlet.doGet(request, response);
        } finally {
            servlet.destroy();
        }
        return request.getForwardUrl();
    }

    @Test
    public void benignPageKeepsEncodedPageParameter() throws Exception {
        final String forwarded = forwardFor("/OrdinaryPage");
        System.out.println("BENCHMARK_CONTROL_FORWARD_URL=" + forwarded);
        Assertions.assertNotNull(forwarded, "servlet must forward an ordinary page request");
        Assertions.assertTrue(forwarded.endsWith("?page=OrdinaryPage&"),
                              () -> "ordinary page parameter changed: " + forwarded);
    }

    @Test
    public void inertWebRootResourceCannotSelectForwardTarget() throws Exception {
        final String forwarded = forwardFor("/templates/210/images/SilkIconSet-readme.txt");
        System.out.println("BENCHMARK_SECURITY_FORWARD_URL=" + forwarded);
        Assertions.assertNotNull(forwarded, "servlet must expose a dispatcher decision");
        Assertions.assertTrue(forwarded.startsWith("/Wiki.jsp?page="),
                              () -> "requested web-root resource selected as dispatcher target: " + forwarded);
    }
}
