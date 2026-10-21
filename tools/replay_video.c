/* Offline video adapter: compile against a frozen game's unmodified renderer
 * and core. Frame schedule changes playback only, never the recorded actions.
 * Build with VIDEO_RENDER_SOURCE and VIDEO_MAIN_SOURCE pointing at that snapshot.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include VIDEO_RENDER_SOURCE
#define main original_interactive_main
#include VIDEO_MAIN_SOURCE
#undef main

#define VIDEO_HEADER 48
#define VIDEO_FOOTER 48
#define VIDEO_H (VIDEO_HEADER + PX_WIN_H + VIDEO_FOOTER)

int main(int argc, char **argv)
{
    if(argc!=5 && argc!=6) { fprintf(stderr,"usage: replay-video TAPE SCHEDULE TITLE SUBTITLE [FOOTER_NOTE]\n"); return 2; }
    /* Optional footer note; without it the original two-video caption is kept. */
    const char *note=argc==6?argv[5]:NULL;
    FILE *raw=fdopen(dup(STDOUT_FILENO),"wb");
    if(!raw || dup2(STDERR_FILENO,STDOUT_FILENO)<0) return 2;
    Tape tape={0};
    if(!tape_load(&tape,argv[1],"replay-video")) return 2;
    FILE *schedule=fopen(argv[2],"r");
    if(!schedule) return 2;
    Env *e=calloc(1,sizeof *e);
    if(!e) return 2;
    EnvConfig cfg={.max_steps=tape.max_steps};
    env_init(e,cfg);env_reset(e,tape.seed);
    SDL_SetMainReady();
    PxUi *ui=px_init(1,NULL);
    if(!ui) return 2;
    SDL_SetWindowSize(ui->win,PX_WIN_W,VIDEO_H);
    SDL_RenderSetLogicalSize(ui->ren,PX_WIN_W,VIDEO_H);
    PxView v={0};Toast toast={0};
    v.hover_recipe=v.hover_ach=v.hover_reach=v.hover_slot=v.hover_item=-1;
    snap_camera(&v,e);
    unsigned char *pixels=malloc((size_t)PX_WIN_W*VIDEO_H*3);
    if(!pixels) return 2;
    int target,last_target=0,last_action=ACT_NOOP,frame_number=0;
    while(fscanf(schedule,"%d",&target)==1) {
        if(target<last_target || target>cfg.max_steps) return 2;
        const double seconds=frame_number/30.0;
        while(tape.i<tape.n && e->steps<target && !e->terminated && !e->truncated) {
            last_action=tape.act[tape.i++];apply(e,last_action,&toast,seconds);
        }
        v.feet_x=(float)e->px;v.feet_y=(float)e->py;
        PxView desired=v;snap_camera(&desired,e);
        v.cam_x+=(desired.cam_x-v.cam_x)*0.30f;
        v.cam_y+=(desired.cam_y-v.cam_y)*0.30f;
        v.clock=seconds;
        v.walk_dir=target==last_target?0:last_action==ACT_LEFT?-1:last_action==ACT_RIGHT?1:0;
        v.airborne=e->jump_left>0 || !tile_solid(tile_at(e,e->px,e->py+1));
        v.toast=toast.until>seconds?toast.text:NULL;v.toast_a=v.toast?1.0f:0.0f;
        SDL_Rect viewport={0,VIDEO_HEADER,PX_WIN_W,PX_WIN_H};
        SDL_RenderSetViewport(ui->ren,&viewport);
        px_draw(ui,e,&v);
        SDL_RenderSetViewport(ui->ren,NULL);
        SDL_RenderSetClipRect(ui->ren,NULL);
        fill(ui,0,0,PX_WIN_W,VIDEO_HEADER,UI_BG);
        fill(ui,0,VIDEO_HEADER+PX_WIN_H,PX_WIN_W,VIDEO_FOOTER,UI_BG);
        SDL_RenderSetScale(ui->ren,2,2);
        text(ui,6,4,UI_ACCENT,argv[3]);
        SDL_RenderSetScale(ui->ren,1,1);
        text(ui,12,31,UI_TEXT,argv[4]);
        int count=0;for(int i=0;i<ACH_COUNT;i++) count+=(e->achievements>>i)&1;
        textf(ui,12,VIDEO_HEADER+PX_WIN_H+7,UI_TEXT,"SEED %llu   ACTION %d/%d   ACHIEVEMENTS %d/%d   HEALTH %d",
              (unsigned long long)tape.seed,e->steps,cfg.max_steps,count,ACH_COUNT,e->health);
        const char *state=e->terminated?"DIED - replay held":e->truncated?"ACTION LIMIT REACHED":tape.i==tape.n?"REPLAY ENDED":"PLAYING";
        if(note) {
            textf(ui,12,VIDEO_HEADER+PX_WIN_H+21,e->terminated?UI_BAD:UI_GOOD,"%s",state);
            text(ui,12,VIDEO_HEADER+PX_WIN_H+35,UI_DIM,note);
        } else {
            textf(ui,12,VIDEO_HEADER+PX_WIN_H+21,e->terminated?UI_BAD:UI_GOOD,"%s | ACTION-SYNCHRONIZED REPLAY; API THINKING TIME OMITTED",state);
            text(ui,12,VIDEO_HEADER+PX_WIN_H+35,UI_DIM,"One illustrative episode, not a benchmark ranking. Same pacing in both videos.");
        }
        SDL_RenderPresent(ui->ren);
        if(SDL_RenderReadPixels(ui->ren,NULL,SDL_PIXELFORMAT_RGB24,pixels,PX_WIN_W*3)!=0) return 2;
        if(fwrite(pixels,3,(size_t)PX_WIN_W*VIDEO_H,raw)!=(size_t)PX_WIN_W*VIDEO_H) return 2;
        last_target=target;frame_number++;
    }
    if(tape.i!=tape.n) { fprintf(stderr,"Schedule did not cover the full tape\n"); return 2; }
    fprintf(stderr,"VIDEO_FINAL {\"steps\":%d,\"health\":%d,\"achievement_mask\":%u,\"return\":%.1f,\"frames\":%d}\n",
            e->steps,e->health,e->achievements,(double)e->ep_return,frame_number);
    fclose(raw);fclose(schedule);free(pixels);px_shutdown(ui);env_free(e);free(e);free(tape.act);
    return 0;
}
