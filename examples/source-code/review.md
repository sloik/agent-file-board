Source remains literal and read-only.

```python
def battery():
    return 90
```

```diff
diff --git a/device.py b/device.py
index 1111111..2222222 100644
--- a/device.py
+++ b/device.py
@@ -1,2 +1,3 @@
 def battery():
-    return 100
+    # Last known reading
+    return 90
```
