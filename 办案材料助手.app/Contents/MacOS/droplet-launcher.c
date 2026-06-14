#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char exe_path[PATH_MAX];
    uint32_t size = sizeof(exe_path);
    if (_NSGetExecutablePath(exe_path, &size) != 0) {
        return 126;
    }

    char *slash = strrchr(exe_path, '/');
    if (slash == NULL) {
        return 126;
    }
    *slash = '\0';

    char script_path[PATH_MAX];
    if (snprintf(script_path, sizeof(script_path), "%s/droplet.sh", exe_path) >= (int)sizeof(script_path)) {
        return 126;
    }

    char **child_argv = calloc((size_t)argc + 2, sizeof(char *));
    if (child_argv == NULL) {
        return 126;
    }
    child_argv[0] = "/bin/bash";
    child_argv[1] = script_path;
    for (int i = 1; i < argc; i++) {
        child_argv[i + 1] = argv[i];
    }
    child_argv[argc + 1] = NULL;

    execv("/bin/bash", child_argv);
    perror("execv");
    return 127;
}
