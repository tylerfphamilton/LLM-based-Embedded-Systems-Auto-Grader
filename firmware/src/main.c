

#include <zephyr/kernel.h>

#include "cmd.h"
#include "link.h"
#include "version.h"

// buffer for the request currently being handled
static struct line req;     // 1 KB: keep it off the stack

int main(void){

    // initialize the link (uart) and check for error
    if (link_init() != 0){

        // No host link, so there is nobody to report to (come back here)
        k_panic();
    }

    // startup message
    link_send_line("# grader-dw " FW_VERSION " reply");

    // forever loop
    for (;;){
        
        // wait for the next complete request line (the thread sleeps here intil the UART interrupt queues a line)
        link_get_line(&req);

        // check to see if there if the data is fragmented
        if (req.too_long){
            link_send_line("ERR BADARG line longer than 1024 bytes");
            continue;
        }

        // parse and execute the request
        cmd_handle(req.text, link_send_line);
    }
    
    return 0;
}