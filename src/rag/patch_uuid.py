import sys
import uuid

# Mock uuid_utils to bypass Windows AppLocker/WDAC DLL block on the binary _uuid_utils.pyd
if 'uuid_utils' not in sys.modules:
    class CompatMock:
        @staticmethod
        def uuid7():
            return uuid.uuid4()
            
    class UUIDUtilsMock:
        compat = CompatMock()
        
    sys.modules['uuid_utils'] = UUIDUtilsMock()
    sys.modules['uuid_utils.compat'] = CompatMock()
