"""The 190 command cases: 32 hand-written originals + 76 generated-grid (materialized, the
generator is retired) + 82 authored realistic. One scorer for every arm.
Case = (name, hebrew, english_reference, expected).
expected: list of (action_type, key, value) per step, in order. value None = any value accepted;
"+"/"-" = sign-only; ("abs", x) = magnitude-only. expected None = open-ended (whitelist-validity
only). expected [] = the correct output is an empty mission (question / negation / not movement).
Keys use the x/y/z names here; the harness maps planner dx/dy/dz output onto them before scoring."""

CASES = [
 ('up10', 'עלה עשרה מטרים', 'go up 10 meters', [('fly_by', 'z', 10)]),
 ('fwd5', 'טוס קדימה חמישה מטרים', 'fly forward 5 meters', [('fly_by', 'x', 5)]),
 ('spin90cw', 'הסתובב תשעים מעלות עם כיוון השעון', 'rotate 90 degrees clockwise', [('spin_by', 'degrees', 90)]),
 ('takeoff', 'המראה', 'take off', [('takeoff', None, None)]),
 ('land', 'נחת', 'land', [('land', None, None)]),
 ('combo3', 'עלה עשרה מטרים, הסתובב תשעים מעלות עם כיוון השעון ואז טוס קדימה חמישה מטרים', 'go up 10 meters, rotate 90 degrees clockwise, then fly forward 5 meters', [('fly_by', 'z', 10), ('spin_by', 'degrees', 90), ('fly_by', 'x', 5)]),
 ('combo_tl', 'המראה, עלה חמישה מטרים, המתן שלוש שניות ונחת', 'take off, go up 5 meters, wait 3 seconds, and land', [('takeoff', None, None), ('fly_by', 'z', 5), ('delay', 'seconds', 3), ('land', None, None)]),
 ('back2left3', 'טוס אחורה שני מטרים ואז שמאלה שלושה מטרים', 'fly backward 2 meters then left 3 meters', [('fly_by', 'x', -2), ('fly_by', 'y', -3)]),
 ('ccw45', 'הסתובב ארבעים וחמש מעלות נגד כיוון השעון', 'rotate 45 degrees counterclockwise', [('spin_by', 'degrees', -45)]),
 ('down3', 'רד שלושה מטרים', 'go down 3 meters', [('fly_by', 'z', -3)]),
 ('question', 'מה אתה רואה עכשיו?', 'what do you see right now?', []),
 ('square', 'טוס בריבוע של שני מטרים', 'fly in a square of 2 meters', None),
 ('up2', 'עלה שני מטרים', 'go up 2 meters', [('fly_by', 'z', 2)]),
 ('right4', 'טוס ימינה ארבעה מטרים', 'fly right 4 meters', [('fly_by', 'y', 4)]),
 ('left7', 'זוז שמאלה שבעה מטרים', 'move left 7 meters', [('fly_by', 'y', -7)]),
 ('back10', 'טוס אחורה עשרה מטרים', 'fly backward 10 meters', [('fly_by', 'x', -10)]),
 ('fwd15', 'התקדם חמישה עשר מטרים', 'advance 15 meters', [('fly_by', 'x', 15)]),
 ('spin180cw', 'הסתובב מאה שמונים מעלות עם כיוון השעון', 'rotate 180 degrees clockwise', [('spin_by', 'degrees', 180)]),
 ('spin360', 'עשה סיבוב שלם עם כיוון השעון', 'do a full turn clockwise', [('spin_by', 'degrees', 360)]),
 ('wait5', 'חכה חמש שניות', 'wait 5 seconds', [('delay', 'seconds', 5)]),
 ('up_half', 'עלה חצי מטר', 'go up half a meter', [('fly_by', 'z', 0.5)]),
 ('combo2b', 'המראה ואז עלה שלושה מטרים', 'take off then go up 3 meters', [('takeoff', None, None), ('fly_by', 'z', 3)]),
 ('combo4', 'טוס קדימה ארבעה מטרים, ימינה שני מטרים, אחורה ארבעה מטרים ואז שמאלה שני מטרים', 'fly forward 4 meters, right 2 meters, backward 4 meters, then left 2 meters', [('fly_by', 'x', 4), ('fly_by', 'y', 2), ('fly_by', 'x', -4), ('fly_by', 'y', -2)]),
 ('combo5', 'המראה, עלה שני מטרים, הסתובב תשעים מעלות עם כיוון השעון, טוס קדימה שלושה מטרים ונחת', 'take off, go up 2 meters, rotate 90 degrees clockwise, fly forward 3 meters, and land', [('takeoff', None, None), ('fly_by', 'z', 2), ('spin_by', 'degrees', 90), ('fly_by', 'x', 3), ('land', None, None)]),
 ('digit12', 'עלה 12 מטרים', 'go up 12 meters', [('fly_by', 'z', 12)]),
 ('digit45deg', 'פנה ימינה 45 מעלות', 'turn right 45 degrees', [('spin_by', 'degrees', 45)]),
 ('question2', 'כמה אנשים אתה רואה', 'how many people do you see', []),
 ('q_land_trap', 'האם אתה מתכוון לנחות בקרוב', 'are you going to land soon', []),
 ('neg_trap', 'אל תטוס קדימה', "don't fly forward", []),
 ('colloq_up', 'תעלה עשרה מטרים', 'climb 10 meters', [('fly_by', 'z', 10)]),
 ('land_now', 'נחת עכשיו', 'land now', [('land', None, None)]),
 ('takeoff_ctx', 'בצע המראה', 'perform takeoff', [('takeoff', None, None)]),
 ('g_up1', 'עלה מטר אחד', 'go up 1 meter', [('fly_by', 'z', 1)]),
 ('g_up2', 'תעלה שני מטרים', 'go up 2 meters', [('fly_by', 'z', 2)]),
 ('g_up3', 'עלה 3 מטרים', 'go up 3 meters', [('fly_by', 'z', 3)]),
 ('g_up4', 'תעלה ארבעה מטרים', 'go up 4 meters', [('fly_by', 'z', 4)]),
 ('g_up6', 'עלה שישה מטרים', 'go up 6 meters', [('fly_by', 'z', 6)]),
 ('g_up8', 'תעלה 8 מטרים', 'go up 8 meters', [('fly_by', 'z', 8)]),
 ('g_up9', 'עלה תשעה מטרים', 'go up 9 meters', [('fly_by', 'z', 9)]),
 ('g_up20', 'תעלה עשרים מטרים', 'go up 20 meters', [('fly_by', 'z', 20)]),
 ('g_up25', 'עלה 25 מטרים', 'go up 25 meters', [('fly_by', 'z', 25)]),
 ('g_down1', 'תרד מטר אחד', 'go down 1 meter', [('fly_by', 'z', -1)]),
 ('g_down2', 'רד 2 מטרים', 'go down 2 meters', [('fly_by', 'z', -2)]),
 ('g_down3', 'תרד שלושה מטרים', 'go down 3 meters', [('fly_by', 'z', -3)]),
 ('g_down4', 'רד ארבעה מטרים', 'go down 4 meters', [('fly_by', 'z', -4)]),
 ('g_down6', 'תרד 6 מטרים', 'go down 6 meters', [('fly_by', 'z', -6)]),
 ('g_down8', 'רד שמונה מטרים', 'go down 8 meters', [('fly_by', 'z', -8)]),
 ('g_down9', 'תרד תשעה מטרים', 'go down 9 meters', [('fly_by', 'z', -9)]),
 ('g_down20', 'רד 20 מטרים', 'go down 20 meters', [('fly_by', 'z', -20)]),
 ('g_down25', 'תרד עשרים וחמישה מטרים', 'go down 25 meters', [('fly_by', 'z', -25)]),
 ('g_fwd1', 'טוס קדימה מטר אחד', 'fly forward 1 meters', [('fly_by', 'x', 1)]),
 ('g_fwd2', 'התקדם שני מטרים', 'fly forward 2 meters', [('fly_by', 'x', 2)]),
 ('g_fwd3', 'טוס קדימה שלושה מטרים', 'fly forward 3 meters', [('fly_by', 'x', 3)]),
 ('g_fwd4', 'התקדם 4 מטרים', 'fly forward 4 meters', [('fly_by', 'x', 4)]),
 ('g_fwd6', 'טוס קדימה שישה מטרים', 'fly forward 6 meters', [('fly_by', 'x', 6)]),
 ('g_fwd8', 'התקדם שמונה מטרים', 'fly forward 8 meters', [('fly_by', 'x', 8)]),
 ('g_fwd9', 'טוס קדימה 9 מטרים', 'fly forward 9 meters', [('fly_by', 'x', 9)]),
 ('g_fwd20', 'התקדם עשרים מטרים', 'fly forward 20 meters', [('fly_by', 'x', 20)]),
 ('g_fwd25', 'טוס קדימה עשרים וחמישה מטרים', 'fly forward 25 meters', [('fly_by', 'x', 25)]),
 ('g_back1', 'זוז אחורה מטר אחד', 'fly backward 1 meter', [('fly_by', 'x', -1)]),
 ('g_back2', 'טוס אחורה שני מטרים', 'fly backward 2 meters', [('fly_by', 'x', -2)]),
 ('g_back3', 'זוז אחורה 3 מטרים', 'fly backward 3 meters', [('fly_by', 'x', -3)]),
 ('g_back4', 'טוס אחורה ארבעה מטרים', 'fly backward 4 meters', [('fly_by', 'x', -4)]),
 ('g_back6', 'זוז אחורה שישה מטרים', 'fly backward 6 meters', [('fly_by', 'x', -6)]),
 ('g_back8', 'טוס אחורה 8 מטרים', 'fly backward 8 meters', [('fly_by', 'x', -8)]),
 ('g_back9', 'זוז אחורה תשעה מטרים', 'fly backward 9 meters', [('fly_by', 'x', -9)]),
 ('g_back20', 'טוס אחורה עשרים מטרים', 'fly backward 20 meters', [('fly_by', 'x', -20)]),
 ('g_back25', 'זוז אחורה 25 מטרים', 'fly backward 25 meters', [('fly_by', 'x', -25)]),
 ('g_right1', 'טוס ימינה מטר אחד', 'fly right 1 meter', [('fly_by', 'y', 1)]),
 ('g_right2', 'זוז ימינה 2 מטרים', 'fly right 2 meters', [('fly_by', 'y', 2)]),
 ('g_right3', 'טוס ימינה שלושה מטרים', 'fly right 3 meters', [('fly_by', 'y', 3)]),
 ('g_right4', 'זוז ימינה ארבעה מטרים', 'fly right 4 meters', [('fly_by', 'y', 4)]),
 ('g_right6', 'טוס ימינה 6 מטרים', 'fly right 6 meters', [('fly_by', 'y', 6)]),
 ('g_right8', 'זוז ימינה שמונה מטרים', 'fly right 8 meters', [('fly_by', 'y', 8)]),
 ('g_right9', 'טוס ימינה תשעה מטרים', 'fly right 9 meters', [('fly_by', 'y', 9)]),
 ('g_right20', 'זוז ימינה 20 מטרים', 'fly right 20 meters', [('fly_by', 'y', 20)]),
 ('g_right25', 'טוס ימינה עשרים וחמישה מטרים', 'fly right 25 meters', [('fly_by', 'y', 25)]),
 ('g_left1', 'זוז שמאלה מטר אחד', 'fly left 1 meters', [('fly_by', 'y', -1)]),
 ('g_left2', 'טוס שמאלה שני מטרים', 'fly left 2 meters', [('fly_by', 'y', -2)]),
 ('g_left3', 'זוז שמאלה שלושה מטרים', 'fly left 3 meters', [('fly_by', 'y', -3)]),
 ('g_left4', 'טוס שמאלה 4 מטרים', 'fly left 4 meters', [('fly_by', 'y', -4)]),
 ('g_left6', 'זוז שמאלה שישה מטרים', 'fly left 6 meters', [('fly_by', 'y', -6)]),
 ('g_left8', 'טוס שמאלה שמונה מטרים', 'fly left 8 meters', [('fly_by', 'y', -8)]),
 ('g_left9', 'זוז שמאלה 9 מטרים', 'fly left 9 meters', [('fly_by', 'y', -9)]),
 ('g_left20', 'טוס שמאלה עשרים מטרים', 'fly left 20 meters', [('fly_by', 'y', -20)]),
 ('g_left25', 'זוז שמאלה עשרים וחמישה מטרים', 'fly left 25 meters', [('fly_by', 'y', -25)]),
 ('g_cw30', 'הסתובב שלושים מעלות עם כיוון השעון', 'rotate 30 degrees clockwise', [('spin_by', 'degrees', 30)]),
 ('g_ccw30', 'הסתובב שלושים מעלות נגד כיוון השעון', 'rotate 30 degrees counterclockwise', [('spin_by', 'degrees', -30)]),
 ('g_cw60', 'הסתובב שישים מעלות עם כיוון השעון', 'rotate 60 degrees clockwise', [('spin_by', 'degrees', 60)]),
 ('g_ccw60', 'הסתובב שישים מעלות נגד כיוון השעון', 'rotate 60 degrees counterclockwise', [('spin_by', 'degrees', -60)]),
 ('g_cw120', 'הסתובב מאה עשרים מעלות עם כיוון השעון', 'rotate 120 degrees clockwise', [('spin_by', 'degrees', 120)]),
 ('g_ccw120', 'הסתובב מאה עשרים מעלות נגד כיוון השעון', 'rotate 120 degrees counterclockwise', [('spin_by', 'degrees', -120)]),
 ('g_cw270', 'הסתובב מאתיים שבעים מעלות עם כיוון השעון', 'rotate 270 degrees clockwise', [('spin_by', 'degrees', 270)]),
 ('g_ccw270', 'הסתובב מאתיים שבעים מעלות נגד כיוון השעון', 'rotate 270 degrees counterclockwise', [('spin_by', 'degrees', -270)]),
 ('g_wait2', 'המתן שתי שניות', 'wait 2 seconds', [('delay', 'seconds', 2)]),
 ('g_wait10', 'המתן עשר שניות', 'wait 10 seconds', [('delay', 'seconds', 10)]),
 ('g_combo2_0', 'עלה מטר אחד ואז תעלה עשרים מטרים', 'go up 1 meter, then go up 20 meters', [('fly_by', 'z', 1), ('fly_by', 'z', 20)]),
 ('g_combo2_1', 'תעלה ארבעה מטרים ואז רד ארבעה מטרים', 'go up 4 meters, then go down 4 meters', [('fly_by', 'z', 4), ('fly_by', 'z', -4)]),
 ('g_combo2_2', 'עלה תשעה מטרים ואז תרד עשרים וחמישה מטרים', 'go up 9 meters, then go down 25 meters', [('fly_by', 'z', 9), ('fly_by', 'z', -25)]),
 ('g_combo2_3', 'תרד מטר אחד ואז טוס קדימה שישה מטרים', 'go down 1 meter, then fly forward 6 meters', [('fly_by', 'z', -1), ('fly_by', 'x', 6)]),
 ('g_combo2_4', 'רד ארבעה מטרים ואז זוז אחורה מטר אחד', 'go down 4 meters, then fly backward 1 meter', [('fly_by', 'z', -4), ('fly_by', 'x', -1)]),
 ('g_combo2_5', 'תרד תשעה מטרים ואז טוס אחורה 8 מטרים', 'go down 9 meters, then fly backward 8 meters', [('fly_by', 'z', -9), ('fly_by', 'x', -8)]),
 ('g_combo2_6', 'טוס קדימה מטר אחד ואז זוז ימינה 2 מטרים', 'fly forward 1 meters, then fly right 2 meters', [('fly_by', 'x', 1), ('fly_by', 'y', 2)]),
 ('g_combo2_7', 'התקדם 4 מטרים ואז טוס ימינה תשעה מטרים', 'fly forward 4 meters, then fly right 9 meters', [('fly_by', 'x', 4), ('fly_by', 'y', 9)]),
 ('g_combo3_0', 'עלה מטר אחד, תעלה ארבעה מטרים ואז תעלה 8 מטרים', 'go up 1 meter, go up 4 meters, then go up 8 meters', [('fly_by', 'z', 1), ('fly_by', 'z', 4), ('fly_by', 'z', 8)]),
 ('g_combo3_1', 'תעלה עשרים מטרים, רד שמונה מטרים ואז טוס קדימה מטר אחד', 'go up 20 meters, go down 8 meters, then fly forward 1 meters', [('fly_by', 'z', 20), ('fly_by', 'z', -8), ('fly_by', 'x', 1)]),
 ('g_combo3_2', 'רד שמונה מטרים, התקדם עשרים מטרים ואז זוז אחורה שישה מטרים', 'go down 8 meters, fly forward 20 meters, then fly backward 6 meters', [('fly_by', 'z', -8), ('fly_by', 'x', 20), ('fly_by', 'x', -6)]),
 ('g_combo3_3', 'התקדם 4 מטרים, טוס ימינה מטר אחד ואז טוס ימינה עשרים וחמישה מטרים', 'fly forward 4 meters, fly right 1 meter, then fly right 25 meters', [('fly_by', 'x', 4), ('fly_by', 'y', 1), ('fly_by', 'y', 25)]),
 ('r_takeoff1', 'תמריא', 'take off', [('takeoff', None, None)]),
 ('r_takeoff2', 'בוא נמריא', "let's take off", [('takeoff', None, None)]),
 ('r_takeoff3', 'אפשר להמריא', 'you can take off', [('takeoff', None, None)]),
 ('r_takeoff4', 'יאללה תמריא', 'come on, take off', [('takeoff', None, None)]),
 ('r_takeoff5', 'תמריא בבקשה', 'take off please', [('takeoff', None, None)]),
 ('r_land1', 'תנחת', 'land', [('land', None, None)]),
 ('r_land2', 'בוא ננחת', "let's land", [('land', None, None)]),
 ('r_land3', 'תנחת בבקשה', 'please land', [('land', None, None)]),
 ('r_land4', 'אפשר לנחות', 'you can land', [('land', None, None)]),
 ('r_land5', 'סיימנו, תנחת', "we're done, land", [('land', None, None)]),
 ('r_pol_up5', 'אתה יכול לעלות חמישה מטרים בבקשה', 'can you go up 5 meters please', [('fly_by', 'z', 5)]),
 ('r_pol_fwd3', 'תוכל לטוס קדימה שלושה מטרים', 'could you fly forward 3 meters', [('fly_by', 'x', 3)]),
 ('r_pol_left2', 'אם אפשר, שני מטרים שמאלה', 'if possible, 2 meters to the left', [('fly_by', 'y', -2)]),
 ('r_pol_down1', 'רד בבקשה מטר אחד', 'please descend 1 meter', [('fly_by', 'z', -1)]),
 ('r_pol_spin', 'תסתובב בבקשה תשעים מעלות ימינה', 'please turn 90 degrees right', [('spin_by', 'degrees', 90)]),
 ('r_fill1', 'אה טוס קדימה שלושה מטרים בבקשה', 'uh fly forward 3 meters please', [('fly_by', 'x', 3)]),
 ('r_fill2', 'אוקיי עכשיו תעלה ארבעה מטרים', 'okay now climb 4 meters', [('fly_by', 'z', 4)]),
 ('r_fill3', 'טוב אז בוא נטוס אחורה שני מטרים', "alright so let's fly back 2 meters", [('fly_by', 'x', -2)]),
 ('r_fill4', 'רגע רגע קודם תעלה שני מטרים', 'wait wait first go up 2 meters', [('fly_by', 'z', 2)]),
 ('r_fill5', 'כן תמשיך ימינה עוד שלושה מטרים', 'yes continue right another 3 meters', [('fly_by', 'y', 3)]),
 ('r_alt10', 'עלה לגובה עשרה מטרים', 'climb to a height of 10 meters', [('fly_by', 'z', 10)]),
 ('r_alt20', 'תעלה לגובה עשרים מטר', 'go up to 20 meters altitude', [('fly_by', 'z', 20)]),
 ('r_low', 'תנמיך שני מטרים', 'descend 2 meters lower', [('fly_by', 'z', -2)]),
 ('r_rise3', 'תתרומם שלושה מטרים', 'rise 3 meters', [('fly_by', 'z', 3)]),
 ('r_updown', 'רד למטה ארבעה מטרים', 'go down 4 meters', [('fly_by', 'z', -4)]),
 ('r_bit_left', 'טוס טיפה שמאלה', 'fly a bit to the left', [('fly_by', 'y', '-')]),
 ('r_bit_up', 'תעלה קצת', 'go up a little', [('fly_by', 'z', '+')]),
 ('r_bit_back', 'זוז קצת אחורה', 'move back a little', [('fly_by', 'x', '-')]),
 ('r_higher', 'תעוף קצת יותר גבוה', 'fly a bit higher', [('fly_by', 'z', '+')]),
 ('r_bit_fwd', 'תתקדם עוד קצת', 'move forward a bit more', [('fly_by', 'x', '+')]),
 ('r_turn_r90', 'סובב את הרחפן תשעים מעלות ימינה', 'turn the drone 90 degrees right', [('spin_by', 'degrees', 90)]),
 ('r_turn_l45', 'תפנה ארבעים וחמש מעלות שמאלה', 'turn 45 degrees left', [('spin_by', 'degrees', -45)]),
 ('r_half_turn', 'תעשה חצי סיבוב', 'do a half turn', [('spin_by', 'degrees', ('abs', 180))]),
 ('r_quart_r', 'רבע סיבוב ימינה', 'quarter turn to the right', [('spin_by', 'degrees', 90)]),
 ('r_full', 'תעשה סיבוב שלם', 'do a full turn', [('spin_by', 'degrees', ('abs', 360))]),
 ('r_around', 'תסתובב אליי', 'turn around toward me', None),
 ('r_num_first', 'שלושים מטר קדימה', '30 meters forward', [('fly_by', 'x', 30)]),
 ('r_m_half', 'מטר וחצי למעלה', 'a meter and a half up', [('fly_by', 'z', 1.5)]),
 ('r_2_half', 'שניים וחצי מטרים ימינה', 'two and a half meters right', [('fly_by', 'y', 2.5)]),
 ('r_digit50', 'טוס קדימה 50 מטר', 'fly forward 50 meters', [('fly_by', 'x', 50)]),
 ('r_digit7', '7 מטרים למעלה', '7 meters up', [('fly_by', 'z', 7)]),
 ('r_meter1', 'זוז מטר ימינה', 'move a meter to the right', [('fly_by', 'y', 1)]),
 ('r_mis1', 'תמריא ותעלה לגובה חמישה מטרים', 'take off and climb to 5 meters', [('takeoff', None, None), ('fly_by', 'z', 5)]),
 ('r_mis2', 'תמריא, עלה שלושה מטרים ותישאר שם', 'take off, go up 3 meters and stay there', [('takeoff', None, None), ('fly_by', 'z', 3)]),
 ('r_mis3', 'טוס ימינה שלושה מטרים ואחרי זה שמאלה שלושה מטרים בחזרה', 'fly right 3 meters and then 3 meters left back', [('fly_by', 'y', 3), ('fly_by', 'y', -3)]),
 ('r_mis4', 'עלה חמישה מטרים, חכה שתי שניות ורד בחזרה', 'go up 5 meters, wait 2 seconds and come back down', [('fly_by', 'z', 5), ('delay', 'seconds', 2), ('fly_by', 'z', -5)]),
 ('r_mis5', 'תמריא, טוס קדימה עשרה מטרים, תסתובב חצי סיבוב וחזור', 'take off, fly forward 10 meters, do a half turn and come back', [('takeoff', None, None), ('fly_by', 'x', 10), ('spin_by', 'degrees', ('abs', 180)), ('fly_by', 'x', 10)]),
 ('r_mis6', 'קדימה שני מטרים ואז למעלה שני מטרים ואז אחורה שני מטרים', 'forward 2 meters then up 2 meters then back 2 meters', [('fly_by', 'x', 2), ('fly_by', 'z', 2), ('fly_by', 'x', -2)]),
 ('r_mis7', 'תעלה עשרה מטרים ואז תסתובב לאט סיבוב שלם', 'climb 10 meters then slowly do a full turn', [('fly_by', 'z', 10), ('spin_by', 'degrees', ('abs', 360))]),
 ('r_mis8', 'אחורה חמישה מטרים ולמטה שני מטרים', 'back 5 meters and down 2 meters', [('fly_by', 'x', -5), ('fly_by', 'z', -2)]),
 ('r_mis9', 'תמריא ואז תנחת', 'take off and then land', [('takeoff', None, None), ('land', None, None)]),
 ('r_mis10', 'עלה שני מטרים, ימינה ארבעה מטרים, שמאלה ארבעה מטרים ורד שני מטרים', 'up 2 meters, right 4 meters, left 4 meters and down 2 meters', [('fly_by', 'z', 2), ('fly_by', 'y', 4), ('fly_by', 'y', -4), ('fly_by', 'z', -2)]),
 ('r_dis1', 'טוס קדימה חמישה מטרים ותצלם את הבית', 'fly forward 5 meters and photograph the house', None),
 ('r_dis2', 'תעלה שלושה מטרים ותסתכל מסביב', 'go up 3 meters and look around', None),
 ('r_dis3', 'תמריא ותחפש את המכונית', 'take off and search for the car', None),
 ('r_dis4', 'טוס ימינה שני מטרים ותגיד לי מה אתה רואה', 'fly right 2 meters and tell me what you see', None),
 ('r_q1', 'מה מצב הסוללה', "what's the battery status", []),
 ('r_q2', 'איפה אתה עכשיו', 'where are you now', []),
 ('r_q3', 'כמה גבוה אתה', 'how high are you', []),
 ('r_q4', 'אתה מצלם', 'are you recording', []),
 ('r_q5', 'ספר לי מה אתה רואה', 'tell me what you see', []),
 ('r_q6', 'יש שם מישהו', 'is anyone there', []),
 ('r_q7', 'כמה זמן נשאר לך באוויר', 'how much flight time do you have left', []),
 ('r_q8', 'אתה שומע אותי', 'can you hear me', []),
 ('r_neg1', 'אל תעלה יותר', "don't go up any more", []),
 ('r_neg2', 'אל תזוז', "don't move", []),
 ('r_neg3', 'לא לטוס קדימה', 'do not fly forward', []),
 ('r_neg4', 'בלי להסתובב בבקשה', 'without turning please', []),
 ('r_neg5', 'אל תנחת עדיין', "don't land yet", []),
 ('r_wait1', 'חכה רגע', 'wait a moment', [('delay', 'seconds', '+')]),
 ('r_wait2', 'שנייה אחת', 'one second', [('delay', 'seconds', '+')]),
 ('r_wait3', 'תמתין חמש שניות ואז רד מטר', 'wait 5 seconds and then descend a meter', [('delay', 'seconds', 5), ('fly_by', 'z', -1)]),
 ('r_wait4', 'עצור שם לעשר שניות', 'hold there for ten seconds', [('delay', 'seconds', 10)]),
 ('r_big100', 'טוס קדימה מאה מטר', 'fly forward 100 meters', [('fly_by', 'x', 100)]),
 ('r_deg10', 'תסתובב עשר מעלות ימינה', 'turn 10 degrees right', [('spin_by', 'degrees', 10)]),
 ('r_deg135', 'פנה מאה שלושים וחמש מעלות שמאלה', 'turn 135 degrees left', [('spin_by', 'degrees', -135)]),
 ('r_z_03', 'תעלה שלושים סנטימטר', 'go up 30 centimeters', [('fly_by', 'z', 0.3)]),
 ('r_back15', 'סע אחורה חמישה עשר מטרים', 'go back 15 meters', [('fly_by', 'x', -15)]),
 ('r_ord1', 'חמישה מטרים קדימה טוס', 'five meters forward, fly', [('fly_by', 'x', 5)]),
 ('r_ord2', 'ימינה שני מטרים', 'right 2 meters', [('fly_by', 'y', 2)]),
 ('r_ord3', 'למעלה, שלושה מטרים', 'upward, 3 meters', [('fly_by', 'z', 3)]),
 ('r_ord4', 'אחורה קצת', 'backward a little', [('fly_by', 'x', '-')]),
]
assert len(CASES) == 190 and len({c[0] for c in CASES}) == 190

ALLOWED = {"takeoff": set(), "land": set(), "fly_by": {"x","y","z"},
           "spin_by": {"degrees"}, "delay": {"seconds"}}

def score(arr, expected):
    if arr is None: return "invalid"
    if expected is None: return "valid(open)"
    if len(arr) != len(expected): return f"wrong-len({len(arr)}vs{len(expected)})"
    for a, (t, k, v) in zip(arr, expected):
        if a["type"] != t: return f"wrong-verb({a['type']}vs{t})"
        if k is not None:
            got = a.get(k)
            if got is None: return f"missing-{k}"
            if v is None: continue
            g = float(got)
            if v == "+":
                if g <= 0: return f"wrong-sign-{k}({got})"
            elif v == "-":
                if g >= 0: return f"wrong-sign-{k}({got})"
            elif isinstance(v, tuple) and v[0] == "abs":
                if abs(abs(g) - v[1]) > 0.01: return f"wrong-abs-{k}({got}vs{v[1]})"
            elif abs(g - float(v)) > 0.01: return f"wrong-{k}({got}vs{v})"
    return "CORRECT"


# ---- verbose multi-step set (54 cases) ----
"""Verbose concatenated command cases (owner refocus 2026-09-02): simple actions with numeric
arguments, chained the way a person actually talks to a machine -- fillers, connectives,
politeness, mixed word/digit numbers (including the measured-weak עשרים family). 12 hand-written
frames x 4 argument fills = 48 linear missions, plus 6 negation/question traps embedded in
verbose phrasing. Deterministic composition, no randomness.
Case = (name, hebrew, english_reference, expected)."""

def _up(n, w, ew):    return (f"עלה {w} מטרים", f"climb {ew} meters", ("fly_by", "z", n))
def _down(n, w, ew):  return (f"רד {w} מטרים", f"descend {ew} meters", ("fly_by", "z", -n))
def _fwd(n, w, ew):   return (f"טוס קדימה {w} מטרים", f"fly forward {ew} meters", ("fly_by", "x", n))
def _back(n, w, ew):  return (f"טוס אחורה {w} מטרים", f"fly backward {ew} meters", ("fly_by", "x", -n))
def _right(n, w, ew): return (f"זוז ימינה {w} מטרים", f"move right {ew} meters", ("fly_by", "y", n))
def _left(n, w, ew):  return (f"זוז שמאלה {w} מטרים", f"move left {ew} meters", ("fly_by", "y", -n))
def _cw(n, w, ew):    return (f"הסתובב {w} מעלות עם כיוון השעון", f"rotate {ew} degrees clockwise", ("spin_by", "degrees", n))
def _turn_r(n, w, ew):return (f"פנה ימינה {w} מעלות", f"turn right {ew} degrees", ("spin_by", "degrees", n))
def _turn_l(n, w, ew):return (f"פנה שמאלה {w} מעלות", f"turn left {ew} degrees", ("spin_by", "degrees", -n))
def _wait(n, w, ew):  return (f"חכה {w} שניות", f"wait {ew} seconds", ("delay", "seconds", n))
TAKEOFF = ("תמריא", "take off", ("takeoff", None, None))
LAND    = ("תנחת", "land", ("land", None, None))

N = {2:("שני","two"), 3:("שלושה","three"), 4:("ארבעה","four"), 5:("חמישה","five"), 6:("שישה","six"),
     7:("שבעה","seven"), 8:("שמונה","eight"), 10:("עשרה","ten"), 12:("12","12"), 15:("חמישה עשר","fifteen"),
     20:("עשרים","twenty"), 25:("עשרים וחמישה","twenty five"), 30:("שלושים","thirty"),
     45:("45","45"), 60:("שישים","sixty"), 90:("תשעים","ninety"), 120:("מאה עשרים","one hundred twenty"),
     180:("מאה שמונים","one hundred eighty")}
def A(fn, n): w, ew = N[n]; return fn(n, w, ew)

# frame = (name-prefix, hebrew format, english format); {0..} are clause slots
FRAMES = [
 ("v_listen3",  "תקשיב, אני רוצה שקודם כל {0}, אחרי זה {1} ואז {2}",
                "Listen, I want you to first {0}, after that {1} and then {2}"),
 ("v_finish3",  "{0}, כשתסיים {1}, ובסוף {2} בבקשה",
                "{0}, when you finish {1}, and at the end {2} please"),
 ("v_start4",   "בוא נתחיל: {0}. עכשיו {1}. יופי, עכשיו {2} וגם {3}",
                "Let's start: {0}. Now {1}. Good, now {2} and also {3}"),
 ("v_okso4",    "אוקיי אז ככה, {0} ואז {1} ואז {2} ואז {3}",
                "Okay so, {0} and then {1} and then {2} and then {3}"),
 ("v_first3",   "קודם {0}, שנייה אחרי זה {1}, ולסיום {2}",
                "First {0}, a second after that {1}, and to finish {2}"),
 ("v_favor4",   "תעשה לי טובה, {0}, אחר כך {1}, אחר כך {2}, ובסוף {3} ותודה",
                "Do me a favor, {0}, afterwards {1}, afterwards {2}, and finally {3}, thanks"),
 ("v_mission3", "המשימה היא כזאת: {0}, לאחר מכן {1}, ואז {2}",
                "The mission is this: {0}, then {1}, and then {2}"),
 ("v_yalla2",   "יאללה {0} ואז {1}",
                "Come on, {0} and then {1}"),
 ("v_ready3",   "רגע, תוודא שאתה מוכן. עכשיו {0}, אחרי זה {1} ואז {2}",
                "Wait, make sure you are ready. Now {0}, after that {1} and then {2}"),
 ("v_seq5",     "אני צריך שתבצע את הרצף הבא: {0}, {1}, {2}, {3}, {4}",
                "I need you to perform the following sequence: {0}, {1}, {2}, {3}, {4}"),
 ("v_note3",    "{0} ואז {1}, ושים לב, {2} לאט ובזהירות",
                "{0} and then {1}, and pay attention, {2} slowly and carefully"),
 ("v_round3",   "טוב, בוא נעשה סיבוב קטן: {0}, {1} ואז {2} וזהו",
                "Alright, let's do a small round: {0}, {1} and then {2} and that's it"),
]
FILLS = [
 [TAKEOFF, A(_up, 5), A(_cw, 90), A(_fwd, 10), LAND],
 [A(_up, 20), A(_turn_r, 45), A(_fwd, 12), A(_wait, 3), LAND],
 [A(_back, 4), A(_left, 3), A(_down, 2), A(_turn_l, 30), A(_wait, 5)],
 [A(_fwd, 25), A(_cw, 180), A(_right, 6), A(_up, 15), A(_down, 8)],
]
VERBOSE_CASES = []
for fi, (name, hf, ef) in enumerate(FRAMES):
    for gi, fill in enumerate(FILLS):
        k = hf.count("{")
        atoms = fill[:k]
        VERBOSE_CASES.append((f"{name}_g{gi}",
            hf.format(*[a[0] for a in atoms]),
            ef.format(*[a[1] for a in atoms]),
            [a[2] for a in atoms]))

VERBOSE_CASES += [
 ("v_neg1", "תקשיב, עלה חמישה מטרים אבל אל תסתובב בינתיים",
            "Listen, climb five meters but do not rotate in the meantime", [("fly_by","z",5)]),
 ("v_neg2", "אוקיי טוס קדימה עשרה מטרים, ובבקשה אל תנחת עדיין",
            "Okay fly forward ten meters, and please do not land yet", [("fly_by","x",10)]),
 ("v_q1",   "לפני שנמשיך, כמה סוללה נשארה לך?",
            "Before we continue, how much battery do you have left?", []),
 ("v_q2",   "רגע רגע, אתה בכלל רואה אותי מפה?",
            "Wait wait, can you even see me from here?", []),
 ("v_mix1", "עלה עשרים מטרים ותגיד לי מה אתה רואה משם",
            "Climb twenty meters and tell me what you see from there", [("fly_by","z",20)]),
 ("v_mix2", "פנה ימינה תשעים מעלות, ואם אתה שומע אותי טוב אז גם טוס קדימה חמישה מטרים",
            "Turn right ninety degrees, and if you hear me well then also fly forward five meters",
            [("spin_by","degrees",90),("fly_by","x",5)]),
]
assert len(VERBOSE_CASES) == 54 and len({c[0] for c in VERBOSE_CASES}) == 54


# ---- stage-0 emergency set: must be caught by the emergency filter, never reach a model ----
EMERGENCY_CASES = [
 ("e_stop", "עצור"), ("e_stopstop", "עצור עצור"), ("e_stop_now", "תעצור עכשיו"),
 ("e_emergency", "חירום חירום"), ("e_stop_all", "עצור הכל בבקשה"), ("e_english", "stop stop stop"),
]
