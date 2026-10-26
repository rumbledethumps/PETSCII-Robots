#ifndef PETSCII_PLATFORM_H
#define PETSCII_PLATFORM_H

/* Called from src/game/platform_bridge.s. */
void plat_key_repeat(void);
void plat_display_control(void);
unsigned char plat_pad_key(void);
unsigned char plat_pad_present(void);
void plat_set_custom_keys(void);
void plat_gamepad_forget_dirs(void);
unsigned char __fastcall__ pad_held(unsigned char button);
unsigned char __fastcall__ pad_pressed(unsigned char button);
void plat_flash_step(void);
void __fastcall__ plat_play_sound(unsigned char effect);
void plat_print_info(void);
void plat_display_item(void);
void plat_display_player_health(void);
void plat_elevator_select(void);
void __fastcall__ plat_demat_palette(unsigned char value);
void __fastcall__ plat_search_dot(unsigned char n);
void plat_scroll_info(void);
void plat_display_weapon(void);
void plat_display_keys(void);
void plat_display_player_sprite(void);
void plat_reverse_tile(void);
void plat_search_glass(void);
void plat_clear_text(void);
void plat_display_intro_screen(void);
void plat_display_game_screen(void);
void plat_reveal_playfield(void);
void plat_display_endgame_screen(void);
void plat_display_menu(void);
void __fastcall__ plat_menu_option(unsigned char row, unsigned char selected);
void plat_display_map_name(void);
void plat_game_over(void);
void __fastcall__ plat_endgame(unsigned char won);
void plat_change_difficulty_level(void);
void plat_menu_flash(void);
void plat_credits_tick(void);
void plat_gamepad_read(void);
void plat_overlay_at(int x, int y, unsigned width, unsigned height,
                     unsigned palette);
void plat_overlay_hide(void);
void __fastcall__ plat_shake(unsigned char dx);

void update_probe(void);

extern unsigned char music_enabled;     /* src/main.c: F6, SHIFT+M */

#endif
