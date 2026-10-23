"""Exact Batch D candidate byte, rights, runtime, and payload-contract boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from corsair import matrix
from corsair.artifacts import ArtifactStore
from corsair.case import load_case, tree_sha256
from corsair.corpus import _patch_sha256, _region_sha256
from corsair.frameworks import framework
from corsair.kernel import Kernel, Submission
from tests.fakes import FakeSandboxes

ROOT = Path(__file__).resolve().parents[1]

CASES = {'cs-1013': {'runtime': 'pytest-cpython312',
             'replay': 'python_replay_pending',
             'repository': 'https://github.com/jpadilla/pyjwt',
             'license_expression': 'MIT',
             'cwe': 'CWE-20',
             'target': {'file': 'jwt/algorithms.py',
                        'symbol': 'HMACAlgorithm.prepare_key',
                        'lines': [193],
                        'fixed_lines': [188]},
             'roles': {'vulnerable': {'commit': '24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc',
                                      'parents': ['31f5acb8fb3ec6cdfe2b1b0a4a8f329b5f3ca67f'],
                                      'git_tree': 'e8496fb90c15e9f45bb89476ed70f8bd3abd72af',
                                      'commit_body_sha256': '1e459d271c2a71d8a729f6ec6a44e96ebb7101eb55618e8fb05aeb899f5a6590',
                                      'archive_sha256': '9ff6178cdd4837474e1dbc636fe76aa227cf66094e0d606f9c3c05e0d53b9117',
                                      'archive_bytes': 62909,
                                      'archive_url': 'https://api.github.com/repos/jpadilla/pyjwt/tarball/24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc',
                                      'upstream_tree_sha256': '1c847cdd2e9efe7c9ce5b51988a97c4b54a7a648e213b648662bbf7ee0d6c892',
                                      'tree_sha256': '1ef00fa83c92e470effbe08fad06126dd90329b655ae45d6442a05bc60201332',
                                      'region_sha256': '644a8f534b0a1afcaf86a8fc008deea1037a7e45798cb3e5555ef1ca92fa874b',
                                      'files': {'jwt/__init__.py': {'mode': '100644',
                                                                    'sha256': 'bdf72143bda227a09a230fedb315d20624ede3a3f761f4fbf0ddf7b77830403d',
                                                                    'bytes': 1548,
                                                                    'blob': 'e692a842ae89ed6c0e0e8a9c6b91f112ee16e0a7'},
                                                'jwt/algorithms.py': {'mode': '100644',
                                                                      'sha256': 'c9e8948582e58998172687e072784b757fe8ed67aa90c1eca8182b37702f1cb0',
                                                                      'bytes': 22388,
                                                                      'blob': '739df808f00e5bb3d2e9474117e99b05479be90e'},
                                                'jwt/api_jwk.py': {'mode': '100644',
                                                                   'sha256': '8d0481d646828b9060c1beccbb4bdf966a8e50261f358471c2d3d0599f444575',
                                                                   'bytes': 3114,
                                                                   'blob': '31250d57f21c8a17ad4c97a3e0c682723dcd5849'},
                                                'jwt/api_jws.py': {'mode': '100644',
                                                                   'sha256': '387145a5dec9e6b7f3a1a8ac4d0173ec2dda860323692ed3b4437dd868c4f013',
                                                                   'bytes': 9186,
                                                                   'blob': 'cbf4f6f5b85dbfdff6f3831ef01d75fe5ffea127'},
                                                'jwt/api_jwt.py': {'mode': '100644',
                                                                   'sha256': '674f4e3e9db4cc1c8e56bb6c30c6db944e78a5f6f8e6d0e87bedd45c5e3c5574',
                                                                   'bytes': 8025,
                                                                   'blob': '7d2177bf535fa739d2efc3b10b44d375b155c5a0'},
                                                'jwt/exceptions.py': {'mode': '100644',
                                                                      'sha256': 'ce9f76f03add47099fe0d615fb34ee6c791bd57a8f6a3d76b2de528bd2cb0cbb',
                                                                      'bytes': 963,
                                                                      'blob': 'ee201add1aac9c778669ed2316286b0fbfa3c30b'},
                                                'jwt/jwks_client.py': {'mode': '100644',
                                                                       'sha256': '783fd67b3496035d8e2fa0659623b5959f59f08382613bb70be0f8671c85da5e',
                                                                       'bytes': 1914,
                                                                       'blob': '767b7179dbb6429a4cc1aa136b6731518115c152'},
                                                'jwt/utils.py': {'mode': '100644',
                                                                 'sha256': '2a08ff87e1bc8c5d0aa311b9de07bc2aa9479c4952788d525b0d081d529c2df2',
                                                                 'bytes': 2471,
                                                                 'blob': '9dde10cf8e539615c66af7740d8dfbae30052a37'}}},
                       'fixed': {'commit': '9c528670c455b8d948aff95ed50e22940d1ad3fc',
                                 'parents': ['24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc'],
                                 'git_tree': '235ecb85818e072ef5377f8e965ef50a41356336',
                                 'commit_body_sha256': 'c50b5009bb628bfcbed5a5878744683f3619e32a435587c3bac4af27f9480e01',
                                 'archive_sha256': '35bec40fc98f0b90d9fb09bd78fce2a9c6129f3a7857b66633bebef464e57524',
                                 'archive_bytes': 65393,
                                 'archive_url': 'https://api.github.com/repos/jpadilla/pyjwt/tarball/9c528670c455b8d948aff95ed50e22940d1ad3fc',
                                 'upstream_tree_sha256': '9a25fef98eb0392b9a255318e0055ffc9c2efcbe4d87d2f441f75215d6c9c53d',
                                 'tree_sha256': 'e7b196b7c513142e08832e1a39c010c0336e7e916f47904855ccdaff6ad62b54',
                                 'region_sha256': 'abf27f656677c79ba9c94fd8e34bd300ea4f7c6e8a6cb289ec4337a26f8bd47e',
                                 'files': {'jwt/__init__.py': {'mode': '100644',
                                                               'sha256': 'b729d36979970b7c209019ed3323189a617d08bed66c4f8e84797730cbf5f064',
                                                               'bytes': 1548,
                                                               'blob': '6b3f8ab160108989240e6cda1a26f76cd9c300c2'},
                                           'jwt/algorithms.py': {'mode': '100644',
                                                                 'sha256': 'e1cf03fe47b4379ca48ba8b4ef30b3893ef4df04957fb09489b424a803d3012f',
                                                                 'bytes': 22392,
                                                                 'blob': '46a1a532e75af58fd596c5e3124068206188c66b'},
                                           'jwt/api_jwk.py': {'mode': '100644',
                                                              'sha256': '8d0481d646828b9060c1beccbb4bdf966a8e50261f358471c2d3d0599f444575',
                                                              'bytes': 3114,
                                                              'blob': '31250d57f21c8a17ad4c97a3e0c682723dcd5849'},
                                           'jwt/api_jws.py': {'mode': '100644',
                                                              'sha256': '387145a5dec9e6b7f3a1a8ac4d0173ec2dda860323692ed3b4437dd868c4f013',
                                                              'bytes': 9186,
                                                              'blob': 'cbf4f6f5b85dbfdff6f3831ef01d75fe5ffea127'},
                                           'jwt/api_jwt.py': {'mode': '100644',
                                                              'sha256': '674f4e3e9db4cc1c8e56bb6c30c6db944e78a5f6f8e6d0e87bedd45c5e3c5574',
                                                              'bytes': 8025,
                                                              'blob': '7d2177bf535fa739d2efc3b10b44d375b155c5a0'},
                                           'jwt/exceptions.py': {'mode': '100644',
                                                                 'sha256': 'ce9f76f03add47099fe0d615fb34ee6c791bd57a8f6a3d76b2de528bd2cb0cbb',
                                                                 'bytes': 963,
                                                                 'blob': 'ee201add1aac9c778669ed2316286b0fbfa3c30b'},
                                           'jwt/jwks_client.py': {'mode': '100644',
                                                                  'sha256': '783fd67b3496035d8e2fa0659623b5959f59f08382613bb70be0f8671c85da5e',
                                                                  'bytes': 1914,
                                                                  'blob': '767b7179dbb6429a4cc1aa136b6731518115c152'},
                                           'jwt/utils.py': {'mode': '100644',
                                                            'sha256': 'd03019f4703a16b196dbc88a717a79eea1b2191f89630600060165f1be11cd27',
                                                            'bytes': 3993,
                                                            'blob': '8ab73b42d32f0e8f4f6b85756e8f0261aaf60418'}}}},
             'evidence': {'evidence/source-vulnerable-LICENSE': {'sha256': '797a7a20231d4c433e9f1911db1731d06b5828b98f499819a034f7c0f56f5ce5',
                                                                 'bytes': 1085,
                                                                 'mode': '100644',
                                                                 'original_path': 'LICENSE',
                                                                 'revision': '24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc',
                                                                 'source_url': 'https://raw.githubusercontent.com/jpadilla/pyjwt/24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc/LICENSE'},
                          'evidence/source-fixed-LICENSE': {'sha256': '797a7a20231d4c433e9f1911db1731d06b5828b98f499819a034f7c0f56f5ce5',
                                                            'bytes': 1085,
                                                            'mode': '100644',
                                                            'original_path': 'LICENSE',
                                                            'revision': '9c528670c455b8d948aff95ed50e22940d1ad3fc',
                                                            'source_url': 'https://raw.githubusercontent.com/jpadilla/pyjwt/9c528670c455b8d948aff95ed50e22940d1ad3fc/LICENSE'}},
             'upstream_patch_sha256': '02f37c4bcd98ab3b65dfa7e04d90bccfa22e546befd74acaa5efdc601fecf76c',
             'patch_sha256': 'c1ff6af4c8ddc77621fd2d496b9e2ec8e361e9ed512b7564408068446af142a5',
             'raw_diff_sha256': '9a336c6dc98c4db4e6a407e4050f6a7241843c3fb7415c40d337c450f6a247dd',
             'raw_diff_bytes': 11177,
             'relationship': 'direct-parent-fix'},
 'cs-1014': {'runtime': 'node-test-node22',
             'replay': 'node22_replay_pending',
             'repository': 'https://github.com/mde/ejs',
             'license_expression': 'Apache-2.0',
             'cwe': 'CWE-94',
             'target': {'file': 'lib/ejs.js',
                        'symbol': 'exports.render',
                        'lines': [415],
                        'fixed_lines': [417]},
             'roles': {'vulnerable': {'commit': '80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1',
                                      'parents': ['abaee2be937236b1b8da9a1f55096c17dda905fd'],
                                      'git_tree': '3da16ae9ed3e20e392c0bc72c97bf1263cfbfe2c',
                                      'commit_body_sha256': '32f85e2a697a0a62cedefde81bf3555357296cf3e041beedbf373b9495513047',
                                      'archive_sha256': '15e16ca592f80fd48ec045904de0461b5c0d80ac36408cbdaf39fe58da73b175',
                                      'archive_bytes': 82758,
                                      'archive_url': 'https://github.com/mde/ejs/archive/80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1.tar.gz',
                                      'upstream_tree_sha256': 'a4ff7a50471df4bbb14d4d35c4af676c8e52ed9446a00f4581c16db6d6876ef0',
                                      'tree_sha256': '61001690d9d0ed381083d940a590ca3dac65c3126d1743af9f97b5ace6ee55fa',
                                      'region_sha256': '703838484fd86db6171711437c1adb9309c808d116ef987837e4d9da8db2d3ec',
                                      'files': {'lib/ejs.js': {'mode': '100755',
                                                               'sha256': '6dbc7b10c4c508fa978c4642bc2b9f3752f98d85c253ab622dda1e7c7758b7e1',
                                                               'bytes': 26680,
                                                               'blob': 'aa6322e304ab6a9a63efeaaf301c792ade243d42'},
                                                'lib/utils.js': {'mode': '100644',
                                                                 'sha256': '3b51eea9f2db2db01189cc9be04833a50ac10ef4809f929e74de1b58763ec5f1',
                                                                 'bytes': 4165,
                                                                 'blob': '284de06624d7a7fb85e1034f9e218c472d717ab8'},
                                                'package.json': {'mode': '100644',
                                                                 'sha256': '694cf5ebe3db8252c12bdb5402dffc5c6d53a16b426c21c2bb583663b93dd500',
                                                                 'bytes': 896,
                                                                 'blob': 'c2b036bead494246533e81248b92d2ea7151336c'}}},
                       'fixed': {'commit': '820855ad75034e303be82c482c5eb8c6616da5c5',
                                 'parents': ['076dcb643c5aed2e10c2847639c98fd923b72854'],
                                 'git_tree': '88eb9cefedf0c8768ed8eb7f16bd8c3e35899bb9',
                                 'commit_body_sha256': '19124a14976f27d1a34e80221079971eba6958764833a87ecb1de0981f944c21',
                                 'archive_sha256': 'f762276dcd40d801e39ac4af76b18b46035d82dd376f85810380a682bf085fa1',
                                 'archive_bytes': 121796,
                                 'archive_url': 'https://github.com/mde/ejs/archive/820855ad75034e303be82c482c5eb8c6616da5c5.tar.gz',
                                 'upstream_tree_sha256': '05add5f15c662a2f2933a11b195069d67e913221bcd4de6116eeebc34882d050',
                                 'tree_sha256': '9c6e511aa6a80500ad5dec86a6f8e7e2c789330dfcc8c6af0d08e659df2b4d18',
                                 'region_sha256': '445ae8fa559547426b82636fa4273bfdddb12daf9873e8bfb1c279da82da90be',
                                 'files': {'lib/ejs.js': {'mode': '100755',
                                                          'sha256': '9ff1cb7fb0a7dbd822e04d35e50560a199926cc323b5aa11f1e89556d7b89814',
                                                          'bytes': 27481,
                                                          'blob': '65590eaed0d7fdf600b08fdc51e90083f5960595'},
                                           'lib/utils.js': {'mode': '100644',
                                                            'sha256': 'eaaf201b085645460dccbc754b024423c1d3b019d9fea8bd9c6b0b8e3785cd82',
                                                            'bytes': 4869,
                                                            'blob': '5aef7c82d783928724fc03b62b54ec5442c5dd1d'},
                                           'package.json': {'mode': '100644',
                                                            'sha256': '8a5250eb30b83f0109c1de33949ecb163ed1bf7e383d3b58ed483d83d13aab12',
                                                            'bytes': 896,
                                                            'blob': '920b01cefcd9b30cb2f5df973183659d52f8c296'}}}},
             'evidence': {'evidence/source-vulnerable-LICENSE': {'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
                                                                 'bytes': 11358,
                                                                 'mode': '100644',
                                                                 'original_path': 'LICENSE',
                                                                 'revision': '80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1',
                                                                 'source_url': 'https://raw.githubusercontent.com/mde/ejs/80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1/LICENSE'},
                          'evidence/source-fixed-LICENSE': {'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
                                                            'bytes': 11358,
                                                            'mode': '100644',
                                                            'original_path': 'LICENSE',
                                                            'revision': '820855ad75034e303be82c482c5eb8c6616da5c5',
                                                            'source_url': 'https://raw.githubusercontent.com/mde/ejs/820855ad75034e303be82c482c5eb8c6616da5c5/LICENSE'}},
             'upstream_patch_sha256': 'b18883424e2d10c5af3b5acc2eb7b364b09f8a42b720a0fc09329bacc2a6bf0f',
             'patch_sha256': '24f234b16e3c5ab14f6692fa572fd9b05bcf8e48bbe07a14c0005da7f0e5591b',
             'raw_diff_sha256': '0592af0314d23551796decf4f2389545eac2a5cd59fee92929491f03fa2e5428',
             'raw_diff_bytes': 215075,
             'relationship': 'release-interval',
             'topology': {'ancestry_commits': 22,
                          'fixed_first_parent_commits': 12,
                          'merge_base': '80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1',
                          'intermediate_commits': ['15ee698583c98dadc456639d6245580d17a24baf',
                                                   'be9a9bb397ed6f4f4e563eed4aa53700f30a837e',
                                                   '576283bb5db2f5b6d2c9f979163a84644f581697'],
                          'release_tags': ['v3.1.6', 'v3.1.7']}},
 'cs-1015': {'runtime': 'javac-java21',
             'replay': 'java21_jacoco_replay_pending',
             'repository': 'https://github.com/apache/commons-text',
             'license_expression': 'Apache-2.0',
             'cwe': 'CWE-200',
             'target': {'file': 'src/main/java/org/apache/commons/text/lookup/StringLookupFactory.java',
                        'symbol': 'StringLookupFactory.addDefaultStringLookups',
                        'lines': [447],
                        'fixed_lines': [462]},
             'roles': {'vulnerable': {'commit': '1c0340694871183baf6e55376dd85c260e810bb0',
                                      'parents': ['58e15aab9b68fc4c80fe25ce710e238a6a6ef2be'],
                                      'git_tree': '057ba3de21048923a88cb97d3f4ea17dc171beb1',
                                      'commit_body_sha256': 'd230212a81fe18b2be500b2619d256fee626900fac05f957e26924472507b605',
                                      'archive_sha256': 'd4054d3c51be265ae543557af435d57aaf1a501747664f046bbdcbc350753fd0',
                                      'archive_bytes': 339066,
                                      'archive_url': 'https://github.com/apache/commons-text/archive/1c0340694871183baf6e55376dd85c260e810bb0.tar.gz',
                                      'upstream_tree_sha256': 'c73d0398f0fbbd340d9413692f812dda13e57a3a8401d22fd0d76332f357c14a',
                                      'tree_sha256': '5d2bd7606785c54e89db20890e413315548f722cfaeb3686d865f218554d354a',
                                      'region_sha256': '230c2c7d2fd69cd5154415b6cb021646d91b2d2fc752f4d8caa017c6c78e0d1c',
                                      'files': {'src/main/java/org/apache/commons/text/Builder.java': {'mode': '100644',
                                                                                                       'sha256': '98902626c87fe305a091128f6978e168a700999c10c0105b6fc9d5b6242912b3',
                                                                                                       'bytes': 2953,
                                                                                                       'blob': '5f5723c0e34fc457666b87dec8d751fe390a4ad0'},
                                                'src/main/java/org/apache/commons/text/StringSubstitutor.java': {'mode': '100644',
                                                                                                                 'sha256': 'c53ddf19ffe26572f925ff9a560f6695d69e57f5f3b73956a8657f26bfc927c7',
                                                                                                                 'bytes': 61356,
                                                                                                                 'blob': '496727501d7014ce0ef1a5ddb9b9947429857f32'},
                                                'src/main/java/org/apache/commons/text/StringTokenizer.java': {'mode': '100644',
                                                                                                               'sha256': '627712ac0cd29d87a903df86cd73c91d1bf416808fdc2b54f69b40ac7ba9c53e',
                                                                                                               'bytes': 38100,
                                                                                                               'blob': '731c468e994cbb6a060d93a58281f42b83622a07'},
                                                'src/main/java/org/apache/commons/text/TextStringBuilder.java': {'mode': '100644',
                                                                                                                 'sha256': '28cd6a0c5fd4afc4bec9e6a85c279abf671f73e328984695fa6074bb1b46d83e',
                                                                                                                 'bytes': 109990,
                                                                                                                 'blob': '21805783726ccf45dc6a4f5c3cf7873fcc4ba698'},
                                                'src/main/java/org/apache/commons/text/lookup/AbstractStringLookup.java': {'mode': '100644',
                                                                                                                           'sha256': '8584bf2174c28411e92ef7d51e633c94201d2f13fcb65ab97c1b9df5b72e6b8f',
                                                                                                                           'bytes': 3015,
                                                                                                                           'blob': '6858ce3ba738b7ec9755485c03c1f5416c0867e2'},
                                                'src/main/java/org/apache/commons/text/lookup/BiFunctionStringLookup.java': {'mode': '100644',
                                                                                                                             'sha256': '6e8c9500de9030cb633d6a7446441d6cc3bff00e0fb8bdc57ec27f703825c207',
                                                                                                                             'bytes': 3446,
                                                                                                                             'blob': '4eba940424ff8ce653ce02aca7aeb1cddc243a98'},
                                                'src/main/java/org/apache/commons/text/lookup/BiStringLookup.java': {'mode': '100644',
                                                                                                                     'sha256': '640303cc327c8a0d38f910e66bc03fd94685b58e8a6ceb698b3e166491d65aba',
                                                                                                                     'bytes': 2907,
                                                                                                                     'blob': 'ac5c879fe56c220d3a1353ab0665eefc7d6158f4'},
                                                'src/main/java/org/apache/commons/text/lookup/ConstantStringLookup.java': {'mode': '100644',
                                                                                                                           'sha256': '949e216ff0e6c585bdf063ecc3f0c2387c5f8056cd79517db4532e8e1c18efe8',
                                                                                                                           'bytes': 5966,
                                                                                                                           'blob': '97bd423904d7ed8fb6b8b3169de3b3a12dfb0be5'},
                                                'src/main/java/org/apache/commons/text/lookup/DateStringLookup.java': {'mode': '100644',
                                                                                                                       'sha256': 'e8b3eaad5076e538a9a7f4ca25489562d9e34cf5b2f4b14b3edd5302e4a77693',
                                                                                                                       'bytes': 3165,
                                                                                                                       'blob': 'a31bbc394639f089ca55bc950a88758461707f1e'},
                                                'src/main/java/org/apache/commons/text/lookup/DefaultStringLookup.java': {'mode': '100644',
                                                                                                                          'sha256': '121017d91615db57b66c05a52d7670acae37728039cbadc84b28ab3cbfc430f5',
                                                                                                                          'bytes': 6006,
                                                                                                                          'blob': 'ce01c81ea342ad410c35bf3903a80efbb4c98010'},
                                                'src/main/java/org/apache/commons/text/lookup/DnsStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': '67ec17a0093a4612483ec92488f6750ca92b99e0e9718a9536c8fcf3b8f5977b',
                                                                                                                      'bytes': 3496,
                                                                                                                      'blob': 'd9e6f9dfcca52a813a891cbcf34082f2fa334595'},
                                                'src/main/java/org/apache/commons/text/lookup/FileStringLookup.java': {'mode': '100644',
                                                                                                                       'sha256': '08e65b4906de1af50651fe10be607ab1c5e04f5e94d0fcba06c69dbd56f04111',
                                                                                                                       'bytes': 2971,
                                                                                                                       'blob': 'e430ea2031a781c37c49c6172c18841d38fd8be5'},
                                                'src/main/java/org/apache/commons/text/lookup/FunctionStringLookup.java': {'mode': '100644',
                                                                                                                           'sha256': 'a8135e263634bb787f159f0cded74e1115bad7901dd08b944cc664d65776194c',
                                                                                                                           'bytes': 3223,
                                                                                                                           'blob': '026ba4bc9f42f1c228308b39480d2793b7cf2449'},
                                                'src/main/java/org/apache/commons/text/lookup/IllegalArgumentExceptions.java': {'mode': '100644',
                                                                                                                                'sha256': 'd810088ee97db2f8991a9402d6f11d17a47c2198d642c07bf01f2c0b2339887c',
                                                                                                                                'bytes': 2316,
                                                                                                                                'blob': '50b3926ca4acf02e0d16838caf2096c7996bb350'},
                                                'src/main/java/org/apache/commons/text/lookup/InetAddressKeys.java': {'mode': '100644',
                                                                                                                      'sha256': 'f57445e51b8335964995c4996f389d1b0e93f02b281890be8c8098fd4eb555fb',
                                                                                                                      'bytes': 1462,
                                                                                                                      'blob': '1b74de6099176311d7386500d9b8dcf1c1bb53ce'},
                                                'src/main/java/org/apache/commons/text/lookup/InterpolatorStringLookup.java': {'mode': '100644',
                                                                                                                               'sha256': '028ac8cf907fa2cbed9fb33ff49b692a4e37e25c31970d38d6be7ac8ae062a04',
                                                                                                                               'bytes': 5486,
                                                                                                                               'blob': '7a63ef61584baacf674c7beccd921c80f0b07fc8'},
                                                'src/main/java/org/apache/commons/text/lookup/JavaPlatformStringLookup.java': {'mode': '100644',
                                                                                                                               'sha256': 'e1d2573b8ecbcee5ca6955ef0f1c36ee4be3aacc74c92c267623707ea1c569d8',
                                                                                                                               'bytes': 8260,
                                                                                                                               'blob': '5339c83f16439ab7760f1796ebc0e4bb30b30874'},
                                                'src/main/java/org/apache/commons/text/lookup/LocalHostStringLookup.java': {'mode': '100644',
                                                                                                                            'sha256': '0e0be62673bd1982c703bb3143cbfe3dc6e478f2b994d2c6654a27f92d34a418',
                                                                                                                            'bytes': 2563,
                                                                                                                            'blob': '20271adbec3c57b723b31a9c898a8444f1916fc9'},
                                                'src/main/java/org/apache/commons/text/lookup/PropertiesStringLookup.java': {'mode': '100644',
                                                                                                                             'sha256': '494901c68551726325968a93ea9c54d66353937d32cd44820e234d8e5ca2f55e',
                                                                                                                             'bytes': 3390,
                                                                                                                             'blob': '7e155dbe52d815484d6a64deddb848d2a6474569'},
                                                'src/main/java/org/apache/commons/text/lookup/ResourceBundleStringLookup.java': {'mode': '100644',
                                                                                                                                 'sha256': '3f7d7007a877b29d7635678d1717bc8d442f39ff5d507872eb94a9e3ee60916d',
                                                                                                                                 'bytes': 4141,
                                                                                                                                 'blob': '7c0a7b067de8ba934170e9330f1737ad3b510276'},
                                                'src/main/java/org/apache/commons/text/lookup/ScriptStringLookup.java': {'mode': '100644',
                                                                                                                         'sha256': 'd98302e9e76422b3c5813a0a1da4ed285895cd3dac38602d563061ef4d603de3',
                                                                                                                         'bytes': 3027,
                                                                                                                         'blob': '3397c9b3c6fa5d21719da5281f6849f8c844fb2e'},
                                                'src/main/java/org/apache/commons/text/lookup/StringLookup.java': {'mode': '100644',
                                                                                                                   'sha256': '18bf77d20cc409cbc56c2c6eb76a81c5014baa5ce486154244c7bada207822eb',
                                                                                                                   'bytes': 2484,
                                                                                                                   'blob': 'df0f2b95a0b63578dcdcf95d929451e2b706f338'},
                                                'src/main/java/org/apache/commons/text/lookup/StringLookupFactory.java': {'mode': '100644',
                                                                                                                          'sha256': '3842b2682cfe70bd91283e155f6083ac7abbaea7fe1dccba159d5252fb306b80',
                                                                                                                          'bytes': 36682,
                                                                                                                          'blob': '54cd61de15fb1fd53f96b52bc4378d60f1bc4d55'},
                                                'src/main/java/org/apache/commons/text/lookup/UrlDecoderStringLookup.java': {'mode': '100644',
                                                                                                                             'sha256': '209ae8f979c8a26f37c50e3da643ceeb29e68f5609cd18485de260f67c5df347',
                                                                                                                             'bytes': 2044,
                                                                                                                             'blob': 'd2b99d4a5c511e837433bd9fc668c7449a495be0'},
                                                'src/main/java/org/apache/commons/text/lookup/UrlEncoderStringLookup.java': {'mode': '100644',
                                                                                                                             'sha256': 'bf4181874db421f490cfb4295989e532a829d3fb971362d0f58b678bf5b67eb9',
                                                                                                                             'bytes': 2016,
                                                                                                                             'blob': '62513aa772e303b335109ca8b72d820e93c63605'},
                                                'src/main/java/org/apache/commons/text/lookup/UrlStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': '47f88161b68de6f64bbe258d1f9a47b9151da1c5c45ccd2a2b48ce434e4604b5',
                                                                                                                      'bytes': 3097,
                                                                                                                      'blob': '1f0ef38eb39b93cc9873ad6dc5bccf95a21a4aa0'},
                                                'src/main/java/org/apache/commons/text/lookup/XmlStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': 'f881d46113e056f195a79e42c2b62923fbd7f20ff6119cda58480190031f0974',
                                                                                                                      'bytes': 2757,
                                                                                                                      'blob': '12aa5e56a453d55f6a8a97591326e15731673ee3'},
                                                'src/main/java/org/apache/commons/text/matcher/AbstractStringMatcher.java': {'mode': '100644',
                                                                                                                             'sha256': '9dc4c3d2e4bf6b58b513911728b36636ba09bb824102b50bc4d7dd9d5f78873f',
                                                                                                                             'bytes': 14169,
                                                                                                                             'blob': '1646b0e73515e79f29bdbd700b3afde7a46f62bc'},
                                                'src/main/java/org/apache/commons/text/matcher/StringMatcher.java': {'mode': '100644',
                                                                                                                     'sha256': '514c762ce3acc0be36de8d65fb0d3b75608a9a8eff3fe001f248db30b8c4b5f8',
                                                                                                                     'bytes': 7081,
                                                                                                                     'blob': '7b82d606c6e48df269d41f5ee6a5e52d906076a1'},
                                                'src/main/java/org/apache/commons/text/matcher/StringMatcherFactory.java': {'mode': '100644',
                                                                                                                            'sha256': '3e0c54bdda5cf5cb0670d35cccee20f12d197ebaad8fcc68bbf7c9ea84014a76',
                                                                                                                            'bytes': 7861,
                                                                                                                            'blob': 'c08b79553b600f201751fd900c2c41dc69c241bb'},
                                                'src/main/resources/org/apache/commons/text/lookup/defaults.properties': {'mode': '100644',
                                                                                                                          'sha256': 'c16e5c1b25ac67939376656a18e00f1e03cc0a09030e975fc34d37af79484b8f',
                                                                                                                          'bytes': 1174,
                                                                                                                          'blob': 'ef2568bc49d81a6ce1c406fbf68ee5906a5fac08'}}},
                       'fixed': {'commit': 'b9b40b903e2d1f9935039803c9852439576780ea',
                                 'parents': ['1c0340694871183baf6e55376dd85c260e810bb0'],
                                 'git_tree': 'c6f7994a270e22998185659c784cc3afcc59674a',
                                 'commit_body_sha256': 'eb95b11443717fe7bb86eec99465d4c4fa3460fd4cedf5060b2739412995e8dd',
                                 'archive_sha256': 'd5572eb02cbafc478dde1ad0adb229a14003a08a90ed1d132bef02f675f1c0ff',
                                 'archive_bytes': 341467,
                                 'archive_url': 'https://github.com/apache/commons-text/archive/b9b40b903e2d1f9935039803c9852439576780ea.tar.gz',
                                 'upstream_tree_sha256': 'dcbeae1b3c21ee89b6b18e92e7eb988e492b54443777d64cf1bc547c23ab1569',
                                 'tree_sha256': 'abc9e9de5e3fe513ff0a4139ac2043babea8cac7f5d279706fde169718991d80',
                                 'region_sha256': 'b7b52479199bbcbd65684faf9eb7e3efbaf27df7e2a29f174bb1673ba5618bba',
                                 'files': {'src/main/java/org/apache/commons/text/Builder.java': {'mode': '100644',
                                                                                                  'sha256': '98902626c87fe305a091128f6978e168a700999c10c0105b6fc9d5b6242912b3',
                                                                                                  'bytes': 2953,
                                                                                                  'blob': '5f5723c0e34fc457666b87dec8d751fe390a4ad0'},
                                           'src/main/java/org/apache/commons/text/StringSubstitutor.java': {'mode': '100644',
                                                                                                            'sha256': '8c4df82b885c1ae1e3761eacb7f91054c5cc4efb10c9eb7026243af306a316cb',
                                                                                                            'bytes': 64029,
                                                                                                            'blob': '3b1e4cb777d8691a95cd7f8ff2341b571db94090'},
                                           'src/main/java/org/apache/commons/text/StringTokenizer.java': {'mode': '100644',
                                                                                                          'sha256': '627712ac0cd29d87a903df86cd73c91d1bf416808fdc2b54f69b40ac7ba9c53e',
                                                                                                          'bytes': 38100,
                                                                                                          'blob': '731c468e994cbb6a060d93a58281f42b83622a07'},
                                           'src/main/java/org/apache/commons/text/TextStringBuilder.java': {'mode': '100644',
                                                                                                            'sha256': '28cd6a0c5fd4afc4bec9e6a85c279abf671f73e328984695fa6074bb1b46d83e',
                                                                                                            'bytes': 109990,
                                                                                                            'blob': '21805783726ccf45dc6a4f5c3cf7873fcc4ba698'},
                                           'src/main/java/org/apache/commons/text/lookup/AbstractStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': '8584bf2174c28411e92ef7d51e633c94201d2f13fcb65ab97c1b9df5b72e6b8f',
                                                                                                                      'bytes': 3015,
                                                                                                                      'blob': '6858ce3ba738b7ec9755485c03c1f5416c0867e2'},
                                           'src/main/java/org/apache/commons/text/lookup/BiFunctionStringLookup.java': {'mode': '100644',
                                                                                                                        'sha256': '6e8c9500de9030cb633d6a7446441d6cc3bff00e0fb8bdc57ec27f703825c207',
                                                                                                                        'bytes': 3446,
                                                                                                                        'blob': '4eba940424ff8ce653ce02aca7aeb1cddc243a98'},
                                           'src/main/java/org/apache/commons/text/lookup/BiStringLookup.java': {'mode': '100644',
                                                                                                                'sha256': '640303cc327c8a0d38f910e66bc03fd94685b58e8a6ceb698b3e166491d65aba',
                                                                                                                'bytes': 2907,
                                                                                                                'blob': 'ac5c879fe56c220d3a1353ab0665eefc7d6158f4'},
                                           'src/main/java/org/apache/commons/text/lookup/ConstantStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': '949e216ff0e6c585bdf063ecc3f0c2387c5f8056cd79517db4532e8e1c18efe8',
                                                                                                                      'bytes': 5966,
                                                                                                                      'blob': '97bd423904d7ed8fb6b8b3169de3b3a12dfb0be5'},
                                           'src/main/java/org/apache/commons/text/lookup/DateStringLookup.java': {'mode': '100644',
                                                                                                                  'sha256': 'e8b3eaad5076e538a9a7f4ca25489562d9e34cf5b2f4b14b3edd5302e4a77693',
                                                                                                                  'bytes': 3165,
                                                                                                                  'blob': 'a31bbc394639f089ca55bc950a88758461707f1e'},
                                           'src/main/java/org/apache/commons/text/lookup/DefaultStringLookup.java': {'mode': '100644',
                                                                                                                     'sha256': 'fb6f3dba881bc88d880777be1380941f5c8db3b94a1ae8d1a682cf52dc0d4d3b',
                                                                                                                     'bytes': 7386,
                                                                                                                     'blob': 'c23d97dd4ec32963563efcb45db5ec6be7cc7e7d'},
                                           'src/main/java/org/apache/commons/text/lookup/DnsStringLookup.java': {'mode': '100644',
                                                                                                                 'sha256': '67ec17a0093a4612483ec92488f6750ca92b99e0e9718a9536c8fcf3b8f5977b',
                                                                                                                 'bytes': 3496,
                                                                                                                 'blob': 'd9e6f9dfcca52a813a891cbcf34082f2fa334595'},
                                           'src/main/java/org/apache/commons/text/lookup/FileStringLookup.java': {'mode': '100644',
                                                                                                                  'sha256': '08e65b4906de1af50651fe10be607ab1c5e04f5e94d0fcba06c69dbd56f04111',
                                                                                                                  'bytes': 2971,
                                                                                                                  'blob': 'e430ea2031a781c37c49c6172c18841d38fd8be5'},
                                           'src/main/java/org/apache/commons/text/lookup/FunctionStringLookup.java': {'mode': '100644',
                                                                                                                      'sha256': 'a8135e263634bb787f159f0cded74e1115bad7901dd08b944cc664d65776194c',
                                                                                                                      'bytes': 3223,
                                                                                                                      'blob': '026ba4bc9f42f1c228308b39480d2793b7cf2449'},
                                           'src/main/java/org/apache/commons/text/lookup/IllegalArgumentExceptions.java': {'mode': '100644',
                                                                                                                           'sha256': 'd810088ee97db2f8991a9402d6f11d17a47c2198d642c07bf01f2c0b2339887c',
                                                                                                                           'bytes': 2316,
                                                                                                                           'blob': '50b3926ca4acf02e0d16838caf2096c7996bb350'},
                                           'src/main/java/org/apache/commons/text/lookup/InetAddressKeys.java': {'mode': '100644',
                                                                                                                 'sha256': 'f57445e51b8335964995c4996f389d1b0e93f02b281890be8c8098fd4eb555fb',
                                                                                                                 'bytes': 1462,
                                                                                                                 'blob': '1b74de6099176311d7386500d9b8dcf1c1bb53ce'},
                                           'src/main/java/org/apache/commons/text/lookup/InterpolatorStringLookup.java': {'mode': '100644',
                                                                                                                          'sha256': '3cc2bc6d1b4ca339ab18144b6719c6bbb1d4d8dcb111b6c63cf850bc0c7d2e17',
                                                                                                                          'bytes': 5405,
                                                                                                                          'blob': '72b36c31feb0889eba735ead026cb39691f94d27'},
                                           'src/main/java/org/apache/commons/text/lookup/JavaPlatformStringLookup.java': {'mode': '100644',
                                                                                                                          'sha256': 'e1d2573b8ecbcee5ca6955ef0f1c36ee4be3aacc74c92c267623707ea1c569d8',
                                                                                                                          'bytes': 8260,
                                                                                                                          'blob': '5339c83f16439ab7760f1796ebc0e4bb30b30874'},
                                           'src/main/java/org/apache/commons/text/lookup/LocalHostStringLookup.java': {'mode': '100644',
                                                                                                                       'sha256': '0e0be62673bd1982c703bb3143cbfe3dc6e478f2b994d2c6654a27f92d34a418',
                                                                                                                       'bytes': 2563,
                                                                                                                       'blob': '20271adbec3c57b723b31a9c898a8444f1916fc9'},
                                           'src/main/java/org/apache/commons/text/lookup/PropertiesStringLookup.java': {'mode': '100644',
                                                                                                                        'sha256': '494901c68551726325968a93ea9c54d66353937d32cd44820e234d8e5ca2f55e',
                                                                                                                        'bytes': 3390,
                                                                                                                        'blob': '7e155dbe52d815484d6a64deddb848d2a6474569'},
                                           'src/main/java/org/apache/commons/text/lookup/ResourceBundleStringLookup.java': {'mode': '100644',
                                                                                                                            'sha256': '3f7d7007a877b29d7635678d1717bc8d442f39ff5d507872eb94a9e3ee60916d',
                                                                                                                            'bytes': 4141,
                                                                                                                            'blob': '7c0a7b067de8ba934170e9330f1737ad3b510276'},
                                           'src/main/java/org/apache/commons/text/lookup/ScriptStringLookup.java': {'mode': '100644',
                                                                                                                    'sha256': 'd98302e9e76422b3c5813a0a1da4ed285895cd3dac38602d563061ef4d603de3',
                                                                                                                    'bytes': 3027,
                                                                                                                    'blob': '3397c9b3c6fa5d21719da5281f6849f8c844fb2e'},
                                           'src/main/java/org/apache/commons/text/lookup/StringLookup.java': {'mode': '100644',
                                                                                                              'sha256': '18bf77d20cc409cbc56c2c6eb76a81c5014baa5ce486154244c7bada207822eb',
                                                                                                              'bytes': 2484,
                                                                                                              'blob': 'df0f2b95a0b63578dcdcf95d929451e2b706f338'},
                                           'src/main/java/org/apache/commons/text/lookup/StringLookupFactory.java': {'mode': '100644',
                                                                                                                     'sha256': '2cd7b54db362a2a398dfdf5c1220979d3900e8977391dc053f046af81e988bb2',
                                                                                                                     'bytes': 45210,
                                                                                                                     'blob': 'bd397f8773c0dd7b6903ec69ae48a99a2c7e7540'},
                                           'src/main/java/org/apache/commons/text/lookup/UrlDecoderStringLookup.java': {'mode': '100644',
                                                                                                                        'sha256': '209ae8f979c8a26f37c50e3da643ceeb29e68f5609cd18485de260f67c5df347',
                                                                                                                        'bytes': 2044,
                                                                                                                        'blob': 'd2b99d4a5c511e837433bd9fc668c7449a495be0'},
                                           'src/main/java/org/apache/commons/text/lookup/UrlEncoderStringLookup.java': {'mode': '100644',
                                                                                                                        'sha256': 'bf4181874db421f490cfb4295989e532a829d3fb971362d0f58b678bf5b67eb9',
                                                                                                                        'bytes': 2016,
                                                                                                                        'blob': '62513aa772e303b335109ca8b72d820e93c63605'},
                                           'src/main/java/org/apache/commons/text/lookup/UrlStringLookup.java': {'mode': '100644',
                                                                                                                 'sha256': '47f88161b68de6f64bbe258d1f9a47b9151da1c5c45ccd2a2b48ce434e4604b5',
                                                                                                                 'bytes': 3097,
                                                                                                                 'blob': '1f0ef38eb39b93cc9873ad6dc5bccf95a21a4aa0'},
                                           'src/main/java/org/apache/commons/text/lookup/XmlStringLookup.java': {'mode': '100644',
                                                                                                                 'sha256': 'f881d46113e056f195a79e42c2b62923fbd7f20ff6119cda58480190031f0974',
                                                                                                                 'bytes': 2757,
                                                                                                                 'blob': '12aa5e56a453d55f6a8a97591326e15731673ee3'},
                                           'src/main/java/org/apache/commons/text/matcher/AbstractStringMatcher.java': {'mode': '100644',
                                                                                                                        'sha256': '9dc4c3d2e4bf6b58b513911728b36636ba09bb824102b50bc4d7dd9d5f78873f',
                                                                                                                        'bytes': 14169,
                                                                                                                        'blob': '1646b0e73515e79f29bdbd700b3afde7a46f62bc'},
                                           'src/main/java/org/apache/commons/text/matcher/StringMatcher.java': {'mode': '100644',
                                                                                                                'sha256': '514c762ce3acc0be36de8d65fb0d3b75608a9a8eff3fe001f248db30b8c4b5f8',
                                                                                                                'bytes': 7081,
                                                                                                                'blob': '7b82d606c6e48df269d41f5ee6a5e52d906076a1'},
                                           'src/main/java/org/apache/commons/text/matcher/StringMatcherFactory.java': {'mode': '100644',
                                                                                                                       'sha256': '3e0c54bdda5cf5cb0670d35cccee20f12d197ebaad8fcc68bbf7c9ea84014a76',
                                                                                                                       'bytes': 7861,
                                                                                                                       'blob': 'c08b79553b600f201751fd900c2c41dc69c241bb'}}}},
             'evidence': {'evidence/source-vulnerable-LICENSE.txt': {'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
                                                                     'bytes': 11358,
                                                                     'mode': '100644',
                                                                     'original_path': 'LICENSE.txt',
                                                                     'revision': '1c0340694871183baf6e55376dd85c260e810bb0',
                                                                     'source_url': 'https://raw.githubusercontent.com/apache/commons-text/1c0340694871183baf6e55376dd85c260e810bb0/LICENSE.txt'},
                          'evidence/source-vulnerable-NOTICE.txt': {'sha256': '9d37a6e7eef7ed9f52cb64cd5327375abd01f5a426776acb14a900958b5d1053',
                                                                    'bytes': 174,
                                                                    'mode': '100644',
                                                                    'original_path': 'NOTICE.txt',
                                                                    'revision': '1c0340694871183baf6e55376dd85c260e810bb0',
                                                                    'source_url': 'https://raw.githubusercontent.com/apache/commons-text/1c0340694871183baf6e55376dd85c260e810bb0/NOTICE.txt'},
                          'evidence/source-vulnerable-pom.xml': {'sha256': '40bdf3b90024ccd41559b08aeded00038c845b6712738cb5574cb6d2dfebfc32',
                                                                 'bytes': 22291,
                                                                 'mode': '100644',
                                                                 'original_path': 'pom.xml',
                                                                 'revision': '1c0340694871183baf6e55376dd85c260e810bb0',
                                                                 'source_url': 'https://raw.githubusercontent.com/apache/commons-text/1c0340694871183baf6e55376dd85c260e810bb0/pom.xml'},
                          'evidence/source-fixed-LICENSE.txt': {'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
                                                                'bytes': 11358,
                                                                'mode': '100644',
                                                                'original_path': 'LICENSE.txt',
                                                                'revision': 'b9b40b903e2d1f9935039803c9852439576780ea',
                                                                'source_url': 'https://raw.githubusercontent.com/apache/commons-text/b9b40b903e2d1f9935039803c9852439576780ea/LICENSE.txt'},
                          'evidence/source-fixed-NOTICE.txt': {'sha256': '9d37a6e7eef7ed9f52cb64cd5327375abd01f5a426776acb14a900958b5d1053',
                                                               'bytes': 174,
                                                               'mode': '100644',
                                                               'original_path': 'NOTICE.txt',
                                                               'revision': 'b9b40b903e2d1f9935039803c9852439576780ea',
                                                               'source_url': 'https://raw.githubusercontent.com/apache/commons-text/b9b40b903e2d1f9935039803c9852439576780ea/NOTICE.txt'},
                          'evidence/source-fixed-pom.xml': {'sha256': '40bdf3b90024ccd41559b08aeded00038c845b6712738cb5574cb6d2dfebfc32',
                                                            'bytes': 22291,
                                                            'mode': '100644',
                                                            'original_path': 'pom.xml',
                                                            'revision': 'b9b40b903e2d1f9935039803c9852439576780ea',
                                                            'source_url': 'https://raw.githubusercontent.com/apache/commons-text/b9b40b903e2d1f9935039803c9852439576780ea/pom.xml'},
                          'evidence/dependency-commons-lang3-3.12.0.pom': {'sha256': '82d31f1dcc4583effd744e979165b16da64bf86bca623fc5d1b03ed94f45c85a',
                                                                           'bytes': 30660,
                                                                           'mode': '100644',
                                                                           'original_path': 'commons-lang3-3.12.0.pom',
                                                                           'revision': '3.12.0',
                                                                           'source_url': 'https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.pom',
                                                                           'coordinate': 'org.apache.commons:commons-lang3:3.12.0',
                                                                           'artifact_sha256': '82d31f1dcc4583effd744e979165b16da64bf86bca623fc5d1b03ed94f45c85a'},
                          'evidence/dependency-commons-lang3-LICENSE.txt': {'sha256': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
                                                                            'bytes': 11358,
                                                                            'mode': '100644',
                                                                            'original_path': 'META-INF/LICENSE.txt',
                                                                            'revision': '3.12.0',
                                                                            'source_url': 'https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar',
                                                                            'coordinate': 'org.apache.commons:commons-lang3:3.12.0',
                                                                            'artifact_sha256': 'd919d904486c037f8d193412da0c92e22a9fa24230b9d67a57855c5c31c7e94e',
                                                                            'archive_member': 'META-INF/LICENSE.txt'},
                          'evidence/dependency-commons-lang3-NOTICE.txt': {'sha256': 'ee00a9534f25e735b92676cff420aa33d3ea196c8642ec93daa264225f3457df',
                                                                           'bytes': 174,
                                                                           'mode': '100644',
                                                                           'original_path': 'META-INF/NOTICE.txt',
                                                                           'revision': '3.12.0',
                                                                           'source_url': 'https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar',
                                                                           'coordinate': 'org.apache.commons:commons-lang3:3.12.0',
                                                                           'artifact_sha256': 'd919d904486c037f8d193412da0c92e22a9fa24230b9d67a57855c5c31c7e94e',
                                                                           'archive_member': 'META-INF/NOTICE.txt'}},
             'upstream_patch_sha256': '54aab7e921fe1cab93e81267dcf9d367874e33b5da436472b5877595cde349fb',
             'patch_sha256': '7de1c5b6d708b985d3ad6c6fd933228014f6dbc42cc3d213166429419a8bb4b1',
             'raw_diff_sha256': 'c4529184735196d353afffa96d76a09cceffd3cb007a395823a8fcf237296c5f',
             'raw_diff_bytes': 67479,
             'relationship': 'direct-parent-fix',
             'dependency_lock': {'java_release': 8,
                                 'compiled_sources': ['src/main/java/org/apache/commons/text/Builder.java',
                                                      'src/main/java/org/apache/commons/text/StringSubstitutor.java',
                                                      'src/main/java/org/apache/commons/text/StringTokenizer.java',
                                                      'src/main/java/org/apache/commons/text/TextStringBuilder.java',
                                                      'src/main/java/org/apache/commons/text/lookup/AbstractStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/BiFunctionStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/BiStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/ConstantStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/DateStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/DefaultStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/DnsStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/FileStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/FunctionStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/IllegalArgumentExceptions.java',
                                                      'src/main/java/org/apache/commons/text/lookup/InetAddressKeys.java',
                                                      'src/main/java/org/apache/commons/text/lookup/InterpolatorStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/JavaPlatformStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/LocalHostStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/PropertiesStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/ResourceBundleStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/ScriptStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/StringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/StringLookupFactory.java',
                                                      'src/main/java/org/apache/commons/text/lookup/UrlDecoderStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/UrlEncoderStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/UrlStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/lookup/XmlStringLookup.java',
                                                      'src/main/java/org/apache/commons/text/matcher/AbstractStringMatcher.java',
                                                      'src/main/java/org/apache/commons/text/matcher/StringMatcher.java',
                                                      'src/main/java/org/apache/commons/text/matcher/StringMatcherFactory.java'],
                                 'vulnerable_only_resource': {'path': 'src/main/resources/org/apache/commons/text/lookup/defaults.properties',
                                                              'sha256': 'c16e5c1b25ac67939376656a18e00f1e03cc0a09030e975fc34d37af79484b8f'},
                                 'artifacts': [{'coordinate': 'org.apache.commons:commons-lang3:3.12.0',
                                                'jar_url': 'https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar',
                                                'jar_sha256': 'd919d904486c037f8d193412da0c92e22a9fa24230b9d67a57855c5c31c7e94e',
                                                'pom_url': 'https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.pom',
                                                'pom_sha256': '82d31f1dcc4583effd744e979165b16da64bf86bca623fc5d1b03ed94f45c85a'}]}},
 'cs-1016': {'runtime': 'perl-tap-540',
             'replay': 'perl_tap_replay_pending',
             'repository': 'https://github.com/nigelm/html-scrubber',
             'license_expression': 'Artistic-1.0-Perl OR GPL-1.0-or-later',
             'cwe': 'CWE-116',
             'target': {'file': 'lib/HTML/Scrubber.pm',
                        'symbol': 'HTML::Scrubber::_scrub_str',
                        'lines': [449],
                        'fixed_lines': [452]},
             'roles': {'vulnerable': {'commit': '2e6f767e1d5a21a6cd4afd75ca03917acf180720',
                                      'parents': ['8e43fd8534302ac9b1cabba544cda266920e7f01'],
                                      'git_tree': '165c97a1330fe65c40bbab0adc347b8432f4f74d',
                                      'commit_body_sha256': '042c5282dfad04cfe079526a4da0226afaaf75be8c01e2113bdd8f10b6df83d9',
                                      'archive_sha256': '133bfff9f086bb02e5aa71217ae29125944a894b71d50ca3cd0df4312d1f0495',
                                      'archive_bytes': 14348,
                                      'archive_url': 'https://codeload.github.com/nigelm/html-scrubber/tar.gz/2e6f767e1d5a21a6cd4afd75ca03917acf180720',
                                      'upstream_tree_sha256': '414798762e56850323c3cd9c684ce5a76fb9bee94f7798fa8ce4ed7597cb09d0',
                                      'tree_sha256': '8576517f2556eb2502bf51a3c962cb4c1930acff57bc3fddaf6150b8deb8c9ae',
                                      'region_sha256': 'd1092eb3fd2b97f747cc8083a9f94d3102e11b60ebfb67418dfbff27d47b55a6',
                                      'files': {'lib/HTML/Scrubber.pm': {'mode': '100644',
                                                                         'sha256': 'f3130a6f6a6374a505c0ec821fc5b5fc7678e8b5494598b87b89d924da66ffe9',
                                                                         'bytes': 18833,
                                                                         'blob': '83221526d0d255eeffced638c8b9b1db661aa8ce'}}},
                       'fixed': {'commit': 'e1978cc37867e85c06a84a4651745235010cd6cd',
                                 'parents': ['2e6f767e1d5a21a6cd4afd75ca03917acf180720'],
                                 'git_tree': '2f14f91122bce09a0e9da331287be2cfcb9c5b7d',
                                 'commit_body_sha256': '59fc7501ccd668585dcd5e1ee60d38387b9e9d25bbadd465be508fdd99626725',
                                 'archive_sha256': '6be15d79565412380ed111b6094f6ff0a7496c41439d24b39463e348c30c857d',
                                 'archive_bytes': 14619,
                                 'archive_url': 'https://codeload.github.com/nigelm/html-scrubber/tar.gz/e1978cc37867e85c06a84a4651745235010cd6cd',
                                 'upstream_tree_sha256': '90cb1e48167ca6b37ca1909b62343096fa534b2a471ee650c004f7af6c8156b0',
                                 'tree_sha256': '5b9fa095859d0e1894b066f3d43d734888fa577432750dfba51f7bf5ede0b284',
                                 'region_sha256': '9eb09b438f9c8cb01b48649b31aaaedd05bdf97695c3e2fa5fb79e3055458e22',
                                 'files': {'lib/HTML/Scrubber.pm': {'mode': '100644',
                                                                    'sha256': '3e237443689db3ec93df02aa85b8fa230c2fff15ec82a0b57ba96226f1d8b5cc',
                                                                    'bytes': 18963,
                                                                    'blob': '2a7b1732c6370f7939079c219c16bdbde1046cfd'}}}},
             'evidence': {'evidence/source-vulnerable-README.pod': {'sha256': '45ead0ef98fa142d371945e7ca00d23d2ea49f34fce46019e8d45c3dbe224401',
                                                                    'bytes': 11549,
                                                                    'mode': '100644',
                                                                    'original_path': 'README.pod',
                                                                    'revision': '2e6f767e1d5a21a6cd4afd75ca03917acf180720',
                                                                    'source_url': 'https://raw.githubusercontent.com/nigelm/html-scrubber/2e6f767e1d5a21a6cd4afd75ca03917acf180720/README.pod'},
                          'evidence/source-vulnerable-dist.ini': {'sha256': '59a5e9175456c98141a3fcaf12a7ea95fa71cc81dd59a2bd4764711670751351',
                                                                  'bytes': 541,
                                                                  'mode': '100644',
                                                                  'original_path': 'dist.ini',
                                                                  'revision': '2e6f767e1d5a21a6cd4afd75ca03917acf180720',
                                                                  'source_url': 'https://raw.githubusercontent.com/nigelm/html-scrubber/2e6f767e1d5a21a6cd4afd75ca03917acf180720/dist.ini'},
                          'evidence/source-fixed-README.pod': {'sha256': '45ead0ef98fa142d371945e7ca00d23d2ea49f34fce46019e8d45c3dbe224401',
                                                               'bytes': 11549,
                                                               'mode': '100644',
                                                               'original_path': 'README.pod',
                                                               'revision': 'e1978cc37867e85c06a84a4651745235010cd6cd',
                                                               'source_url': 'https://raw.githubusercontent.com/nigelm/html-scrubber/e1978cc37867e85c06a84a4651745235010cd6cd/README.pod'},
                          'evidence/source-fixed-dist.ini': {'sha256': '59a5e9175456c98141a3fcaf12a7ea95fa71cc81dd59a2bd4764711670751351',
                                                             'bytes': 541,
                                                             'mode': '100644',
                                                             'original_path': 'dist.ini',
                                                             'revision': 'e1978cc37867e85c06a84a4651745235010cd6cd',
                                                             'source_url': 'https://raw.githubusercontent.com/nigelm/html-scrubber/e1978cc37867e85c06a84a4651745235010cd6cd/dist.ini'},
                          'evidence/Perl-5.12.3-Artistic': {'sha256': 'b7fd9b73ea99602016a326e0b62e6646060d18febdd065ceca8bb482208c3d88',
                                                            'bytes': 6111,
                                                            'mode': '100644',
                                                            'original_path': 'Artistic',
                                                            'revision': 'c0247066c34077145eaa8f33eddcbb64fa3b0f8d',
                                                            'source_url': 'https://raw.githubusercontent.com/Perl/perl5/c0247066c34077145eaa8f33eddcbb64fa3b0f8d/Artistic'}},
             'upstream_patch_sha256': 'ecd3c76418a16e5010127b5ebb9a6ee4fc7c0688255be4b36dfd0b00027fe0ba',
             'patch_sha256': '5d10143c2b8ab2c152963bc82e388251fe751340e7ce83d5f655b1647961b7c4',
             'raw_diff_sha256': '61ea402eba35671666625a86976332aa5184d110aeaf555cc54a2859e7bde77e',
             'raw_diff_bytes': 1915,
             'relationship': 'direct-parent-fix'}}


def read(case_id, name):
    path = ROOT / 'cases' / case_id / name
    assert path.is_file(), f'missing Batch D asset: {case_id}/{name}'
    return json.loads(path.read_bytes())


@pytest.mark.parametrize('case_id', CASES)
def test_batch_d_exact_source_bytes_modes_and_revision_identities(case_id):
    expected = CASES[case_id]
    assets = read(case_id, 'asset-manifest.json')
    directory = ROOT / 'cases' / case_id
    case = load_case(directory)
    assert assets['schema'] == 'corsair-lite/case-assets/1'
    assert assets['case_id'] == case_id
    assert assets['family_id'] == case_id.replace('cs-', 'cf-')
    assert assets['repository'] == expected['repository']
    assert assets['source_closure'] == sorted(expected['roles']['vulnerable']['files'])
    assert assets['role_source_closure'] == {role: sorted(data['files']) for role, data in expected['roles'].items()}
    assert assets['target'] == expected['target'], 'revision-specific executable target map drifted'
    assert assets['upstream_source_pair']['relationship'] == expected['relationship']
    assert assets['upstream_source_pair']['patch_sha256'] == expected['upstream_patch_sha256']
    assert assets['upstream_source_pair']['raw_diff_sha256'] == expected['raw_diff_sha256']
    assert assets['upstream_source_pair']['raw_diff_bytes'] == expected['raw_diff_bytes']
    assert assets['vendored_source_pair']['patch_sha256'] == expected['patch_sha256']
    assert assets.get('topology') == expected.get('topology')
    for role, revision in [('vulnerable', case.revision), ('fixed', case.fixed_revision)]:
        data = expected['roles'][role]
        root = directory / role
        assert revision.commit == data['commit']
        assert revision.tree_sha256 == data['tree_sha256'] == tree_sha256(root)
        assert not any(path.is_symlink() for path in root.rglob('*')), 'source links forbidden'
        assert sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()) == sorted(data['files']), 'source closure has missing/extra files'
        assert assets['source_files'][role] == data['files'], 'source hash/length/mode/blob map drifted'
        upstream = assets['upstream_source_pair'][role]
        assert upstream == {key: data[key] for key in ['commit', 'parents', 'git_tree', 'commit_body_sha256', 'archive_sha256', 'archive_bytes', 'archive_url', 'upstream_tree_sha256']}
        assert assets['vendored_source_pair'][role] == {key: data[key] for key in ['tree_sha256', 'region_sha256']}
        for relative, identity in data['files'].items():
            path = root / relative
            content = path.read_bytes()
            assert hashlib.sha256(content).hexdigest() == identity['sha256'], f'source hash: {role}/{relative}'
            assert len(content) == identity['bytes'], f'source size: {role}/{relative}'
            assert ('100755' if path.stat().st_mode & 0o111 else '100644') == identity['mode'], f'source mode: {role}/{relative}'
            assert hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() == identity['blob']
        lines = expected['target']['lines' if role == 'vulnerable' else 'fixed_lines']
        assert _region_sha256(root / expected['target']['file'], tuple(lines)) == data['region_sha256']
    assert _patch_sha256(directory / 'vulnerable', directory / 'fixed') == expected['patch_sha256']


@pytest.mark.parametrize('case_id', CASES)
def test_batch_d_exact_evidence_origins_rights_and_closed_inventory(case_id):
    expected = CASES[case_id]
    assets = read(case_id, 'asset-manifest.json')
    directory = ROOT / 'cases' / case_id
    assert assets['evidence'] == expected['evidence'], 'evidence origins or identities drifted'
    expected_inventory = {'input.json', 'oracle.json', 'reference-submission.json', 'asset-manifest.json'}
    if case_id == 'cs-1015': expected_inventory.add('dependencies.lock')
    expected_inventory.update(expected['evidence'])
    expected_inventory.update(f'{role}/{path}' for role, data in expected['roles'].items() for path in data['files'])
    actual_inventory = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    assert actual_inventory == expected_inventory, 'case inventory has missing/extra files'
    assert not any(path.is_symlink() for path in directory.rglob('*')), 'case links forbidden'
    for relative, identity in expected['evidence'].items():
        path = directory / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == identity['sha256'], f'evidence hash: {relative}'
        assert len(path.read_bytes()) == identity['bytes']
        assert ('100755' if path.stat().st_mode & 0o111 else '100644') == identity['mode']
    rights = assets['rights_review']
    assert rights['reviewer'] == 'OpenAI Codex automated factual rights preparation'
    assert rights['reviewed_at'] == '2026-10-23'
    assert rights['review_kind'] == 'automated_factual'
    assert rights['human_legal_approval'] is False
    assert rights['scope'] == 'Byte-exact selected source subsets and copied evidence only; runtime rights, independent review, replay and admission remain pending.'
    components = rights['components']
    covered = [path for component in components for path in component['covered_paths']]
    required = expected_inventory - {'input.json', 'oracle.json', 'reference-submission.json', 'asset-manifest.json', 'dependencies.lock'}
    assert set(covered) == required and len(covered) == len(required), 'rights coverage incomplete, duplicated or broadened'
    for component in components:
        assert component['license_evidence_paths'] and component['notice_requirements']
        assert set(component['license_evidence_paths']) <= set(expected['evidence'])
    source = components[0]
    assert source['license_expression'] == expected['license_expression']
    assert source['redistribution_mode'] == 'verbatim source subset with exact revision-local evidence'
    if case_id == 'cs-1016':
        assert source['license_election'] == 'Artistic-1.0-Perl'
        assert set(source['license_evidence_paths']) == set(expected['evidence'])
        assert assets['runtime_facts']['packages'] == ['libhtml-parser-perl:amd64=3.83-2~deb13u1', 'libhtml-tagset-perl=3.24-1', 'liburi-perl=5.30-1', 'perl=5.40.1-6+deb13u1', 'perl-base=5.40.1-6+deb13u1', 'perl-modules-5.40=5.40.1-6+deb13u1', 'libperl5.40:amd64=5.40.1-6+deb13u1']
    if case_id == 'cs-1013':
        assert 'Copyright (c) 2015-2022 José Padilla' in (directory / 'evidence/source-vulnerable-LICENSE').read_text()
        assert not any('NOTICE' in path for path in expected['evidence'])
    if case_id == 'cs-1014':
        assert 'Copyright 2112 Matthew Eernisse' in (directory / 'vulnerable/lib/ejs.js').read_text()
        assert not any('NOTICE' in path for path in expected['evidence'])
    if case_id == 'cs-1015':
        assert '2014-2022' in (directory / 'evidence/source-vulnerable-NOTICE.txt').read_text()
        assert '2001-2021' in (directory / 'evidence/dependency-commons-lang3-NOTICE.txt').read_text()
        assert components[1]['license_expression'] == 'Apache-2.0'


RUNTIMES = {
    'cs-1013': ('sha256:43b0c43a93350375aa45a6ac664489826fce01599daae81dbc10127e4854110a', 'Python 3.12.15'),
    'cs-1014': ('sha256:0c057726aa5f32ca5e8b6793c2f0d40dfe1f9492dded237d7c1e14bc0a5401e1', 'Node v22.23.3'),
    'cs-1015': ('sha256:e09616f1ef5468b518d42719c99561f6944b4d8e8dfd7d56345c9272afe5532d', 'Temurin OpenJDK 21.0.12.1+1'),
    'cs-1016': ('sha256:90a29df261025b1c1e0d001373e10393ccc9c14f00b7baa14dc19a88c1c6b37f', 'Perl v5.40.1'),
}


@pytest.mark.parametrize('case_id', CASES)
def test_batch_d_candidate_submission_runtime_and_oracle_boundary(case_id, tmp_path):
    expected = CASES[case_id]
    directory = ROOT / 'cases' / case_id
    assets = read(case_id, 'asset-manifest.json')
    request = read(case_id, 'input.json')
    oracle = read(case_id, 'oracle.json')
    reference = read(case_id, 'reference-submission.json')
    case = load_case(directory)
    submission = Submission.model_validate(reference)
    assert reference['contract_version'] == 'corsair-lite/differential-probe/2'
    assert framework(matrix.select(case).framework).guard(submission.probe).passed
    assert matrix.select(case).id == expected['runtime']
    assert assets['runtime_facts']['runtime_id'] == expected['runtime']
    assert (assets['runtime_facts']['preparation_image_id'], assets['runtime_facts']['version']) == RUNTIMES[case_id]
    assert assets['runtime_facts']['rights_status'] == 'pending'
    assert request['finding']['cwe'] == expected['cwe']
    assert request['finding']['file_path'] == submission.hypothesis.target_file == expected['target']['file']
    assert request['finding']['start_line'] == expected['target']['lines'][0]
    assert submission.hypothesis.target_symbol == expected['target']['symbol']
    assert submission.hypothesis.target_lines == tuple(expected['target']['lines'])
    assert 'fixed_target_lines' not in reference['hypothesis']
    evaluator = Kernel(FakeSandboxes({}), matrix.select(case), case,
                       artifacts=ArtifactStore(tmp_path / 'artifacts'),
                       fixed_target_lines=tuple(assets['target']['fixed_lines']))
    assert evaluator._revision_hypothesis(submission.hypothesis, 'vulnerable').target_lines == tuple(expected['target']['lines'])
    assert evaluator._revision_hypothesis(submission.hypothesis, 'fixed').target_lines == tuple(expected['target']['fixed_lines'])
    assert submission.hypothesis.target_lines == tuple(expected['target']['lines'])
    assert assets['qualification_status'] == oracle['qualification_status'] == 'candidate'
    assert set(assets['qualification_blockers']) == {'dataset_manifest_entry_pending', 'runtime_rights_pending', 'independent_review_pending', expected['replay']}
    assert oracle['dataset_version'] == 'batch-d-candidate/1'
    assert oracle['expected_label'] == 'LIKELY_EXPLOITABLE' and oracle['expected_fix'] == 'verified'
    assert 'kernel evidence/admission remain pending' in oracle['note']
    assert set(request) == {'case_id', 'finding', 'source', 'commit', 'fixed_source', 'fixed_commit'}
    assert set(case.model_dump()).isdisjoint({'expected_label', 'expected_fix', 'oracle', 'qualification_status'})
    for term in ['LIKELY_EXPLOITABLE', 'verified', 'qualification_status', 'oracle']:
        assert term not in case.model_dump_json()
        assert term not in submission.probe
    manifest = json.loads((ROOT / 'benchmarks/dataset/manifest.json').read_bytes())
    assert case_id not in json.dumps(manifest)
    if case_id != 'cs-1015': assert reference['build_script'] == ''


def test_batch_d_java_dependency_lock_is_exact_and_build_is_closed():
    expected = CASES['cs-1015']['dependency_lock']
    lock = read('cs-1015', 'dependencies.lock')
    assets = read('cs-1015', 'asset-manifest.json')
    assert lock == expected
    assert assets['dependency_lock'] == {'path': 'dependencies.lock', **expected}
    build = read('cs-1015', 'reference-submission.json')['build_script']
    assert 'javac --release 8 -encoding UTF-8 -g -sourcepath /nonexistent' in build
    assert expected['artifacts'][0]['jar_url'] in build
    assert expected['artifacts'][0]['jar_sha256'] in build and 'sha256sum -c -' in build
    assert all('/work/' + path in build for path in expected['compiled_sources'])
    assert expected['vulnerable_only_resource']['path'] in build
    assert not any(term in build.lower() for term in ['mvn ', 'maven ', 'npm ', '*.java', '-sources.jar'])


def test_batch_d_probes_keep_safe_owned_payload_only_invariants():
    probes = {case: read(case, 'reference-submission.json')['probe'] for case in CASES}
    py = probes['cs-1013']
    assert 'def run_target(payload' in py and 'accepted != asymmetric' in py
    assert 'except InvalidKeyError:' in py and 'HMACAlgorithm(hashlib.sha256).prepare_key(key)' in py
    assert 'os.urandom(32)' in py and 'base64.b64decode(encoded, validate=True)' in py
    assert 'cryptography' not in py
    js = probes['cs-1014']
    assert "ejs.render('<%= value %>', {value: 'OK'}, null)" in js
    assert 'finally' in js and 'delete Object.prototype.outputFunctionName' in js
    assert 'return marker.changed === false' in js
    assert "'ownedOutput'" in js and 'x;globalThis.__corsairEjsOwned.changed=true;var y' in js
    assert not any(term in js for term in ['child_process', 'execSync', 'writeFile', 'fetch('])
    java = probes['cs-1015']
    assert 'expected.equals(actual) && !forbidden.equals(actual)' in java
    assert 'StringSubstitutor.createInterpolator().replace(input)' in java
    assert 'Files.createTempFile' in java and 'Files.delete(owned)' in java and 'finally' in java
    assert 'defaultStringLookups' in java and 'owned-local-marker' in java
    assert not any(term in java for term in ['Runtime.getRuntime', 'ProcessBuilder', 'http:', 'https:', 'script:'])
    perl = probes['cs-1016']
    assert 'HTML::Scrubber->new(comment => 1)' in perl
    assert '<!--owned complete note-->' in perl and '<!--owned incomplete note' in perl
    assert "$output eq $payload->{expected}" in perl
    assert 'unless defined $output && !ref $output' in perl
