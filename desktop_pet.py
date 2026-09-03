from __future__ import annotations
import ctypes
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from PIL import Image, ImageFilter, ImageTk

APP_NAME="MyBichonDesktopPet"
TRANSPARENT="#010101"
SIDE_STATES={"idle":0,"walk":1,"run":2,"pant_side":3}
FRONT_STATES={"front":0,"sit":1,"happy":2,"pant":3}
COMMON_COLLECTIBLES={
    "돌멩이":"🪨","뼈다귀":"🦴","나뭇잎":"🍃","공":"🎾","나뭇가지":"🪵",
    "꽃":"🌼","도토리":"🌰","솔방울":"🌲","깃털":"🪶","조개껍데기":"🐚",
    "리본":"🎀","낡은 양말":"🧦","반짝이는 단추":"🔘","작은 방울":"🔔",
    "클로버":"🍀","유리구슬":"🔮",
}
RARE_COLLECTIBLES={
    "은빛 뼈다귀":"🩶","별 조각":"⭐","무지개 리본":"🌈",
    "보석 목걸이":"💎","행운의 금빛 방울":"🔔","푸른 수정":"🔷",
}
ULTRA_RARE_COLLECTIBLES={
    "황금 뼈다귀":"👑","전설의 별사탕":"🌟","오로라 보석":"🌌",
}
COLLECTIBLES={**COMMON_COLLECTIBLES,**RARE_COLLECTIBLES,**ULTRA_RARE_COLLECTIBLES}
FRIENDS=["동네 비숑","말티즈 친구","푸들 친구","용감한 시바","큰 골든리트리버"]

def collectible_rarity_and_chance(name:str)->tuple[str,str]:
    if name in ULTRA_RARE_COLLECTIBLES:
        return "초희귀",f"{0.1/len(ULTRA_RARE_COLLECTIBLES):.4f}%"
    if name in RARE_COLLECTIBLES:
        return "레어",f"{1.1/len(RARE_COLLECTIBLES):.4f}%"
    return "일반",f"{98.8/len(COMMON_COLLECTIBLES):.3f}%"

def enable_dpi_awareness()->None:
    if sys.platform!="win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError,OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError,OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError,OSError):
                pass

def resource_path(relative:str)->Path:
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))/relative

def settings_path()->Path:
    return Path(os.getenv("LOCALAPPDATA") or Path.home())/APP_NAME/"settings.json"

@dataclass
class Settings:
    configured:bool=False
    name:str="구름이"
    size_percent:int=100
    affection:int=30
    hunger:int=80
    energy:int=80
    mood:int=70
    level:int=1
    exp:int=0
    auto_start:bool=False
    show_speech_bubbles:bool=True
    follow_mouse:bool=False
    stay_sitting:bool=False
    x:int=-1
    surface_hwnd:int=0
    surface_offset_y:int=0
    collection:dict[str,int]=field(default_factory=dict)
    adventures:int=0
    fights:int=0
    wins:int=0
    adventure_log_date:str=""
    adventure_log:list[dict[str,str]]=field(default_factory=list)

    @classmethod
    def load(cls)->"Settings":
        try:
            raw=json.loads(settings_path().read_text(encoding="utf-8"))
            return cls(**{k:v for k,v in raw.items() if k in cls.__dataclass_fields__})
        except (OSError,ValueError,TypeError):
            return cls()

    def save(self)->None:
        path=settings_path()
        path.parent.mkdir(parents=True,exist_ok=True)
        temp_path=path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(asdict(self),ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(temp_path,path)

def set_auto_start(enabled:bool)->None:
    if sys.platform!="win32":
        return
    import winreg
    target=Path(sys.executable if getattr(sys,"frozen",False) else __file__).resolve()
    command=f'"{target}"' if getattr(sys,"frozen",False) else f'"{sys.executable}" "{target}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Run",0,winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key,APP_NAME,0,winreg.REG_SZ,command)
        else:
            try:
                winreg.DeleteValue(key,APP_NAME)
            except FileNotFoundError:
                pass

def remove_edge_fringe(image:Image.Image)->Image.Image:
    image=image.convert("RGBA")
    pixels=image.load()
    for y in range(image.height):
        for x in range(image.width):
            red,green,blue,alpha=pixels[x,y]
            green_over=green-max(red,blue)
            if green_over>4:
                green=min(green,max(red,blue)+2)
                alpha=int(alpha*max(0.0,1.0-green_over/55.0))
            if alpha<35:
                alpha=0
            pixels[x,y]=red,green,blue,alpha
    return image

def resize_sprite(image:Image.Image,max_size:int)->Image.Image:
    image=remove_edge_fringe(image)
    ratio=min(max_size/image.width,max_size/image.height,1.0)
    target=(max(1,round(image.width*ratio)),max(1,round(image.height*ratio)))
    image=image.convert("RGBa").resize(target,Image.Resampling.LANCZOS).convert("RGBA")
    alpha=image.getchannel("A").point(lambda value:255 if value>=105 else 0)
    inner=alpha.filter(ImageFilter.MinFilter(3))
    pixels=image.load()
    alpha_pixels=alpha.load()
    inner_pixels=inner.load()
    for y in range(image.height):
        for x in range(image.width):
            if alpha_pixels[x,y] and not inner_pixels[x,y]:
                red,green,blue,_=pixels[x,y]
                if red+green+blue<570:
                    pixels[x,y]=(max(red,205),max(green,205),max(blue,200),255)
    image.putalpha(alpha)
    return image

class Rect(ctypes.Structure):
    _fields_=[("left",ctypes.c_long),("top",ctypes.c_long),("right",ctypes.c_long),("bottom",ctypes.c_long)]

class Point(ctypes.Structure):
    _fields_=[("x",ctypes.c_long),("y",ctypes.c_long)]

class MonitorInfo(ctypes.Structure):
    _fields_=[("cbSize",wintypes.DWORD),("rcMonitor",Rect),("rcWork",Rect),("dwFlags",wintypes.DWORD)]

class WindowsSurface:
    def __init__(self,own_hwnd_getter):
        self.own_hwnd_getter=own_hwnd_getter
        self.user32=ctypes.windll.user32 if sys.platform=="win32" else None
        if self.user32:
            self.user32.GetAncestor.restype=wintypes.HWND
            self.user32.IsWindow.argtypes=[wintypes.HWND]
            self.user32.IsWindowVisible.argtypes=[wintypes.HWND]
            self.user32.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(Rect)]
            self.user32.MonitorFromPoint.restype=wintypes.HMONITOR
            self.user32.MonitorFromPoint.argtypes=[Point,wintypes.DWORD]
            self.user32.GetMonitorInfoW.argtypes=[wintypes.HMONITOR,ctypes.POINTER(MonitorInfo)]
            self.user32.GetCursorPos.argtypes=[ctypes.POINTER(Point)]
            self.user32.WindowFromPoint.argtypes=[Point]
            self.user32.WindowFromPoint.restype=wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
            self.user32.GetWindowThreadProcessId.restype=wintypes.DWORD
            self.user32.SetWindowPos.argtypes=[
                wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                ctypes.c_int,ctypes.c_int,wintypes.UINT
            ]
            self.user32.SetWindowPos.restype=wintypes.BOOL

    def work_area(self)->tuple[int,int,int,int]:
        if not self.user32:
            return 0,0,1920,1040
        rect=Rect()
        self.user32.SystemParametersInfoW(0x0030,0,ctypes.byref(rect),0)
        return rect.left,rect.top,rect.right,rect.bottom

    def monitor_work_areas(self)->list[tuple[int,int,int,int]]:
        if not self.user32:
            return [(0,0,1920,1040)]
        areas=[]
        @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HMONITOR,wintypes.HDC,ctypes.POINTER(Rect),wintypes.LPARAM)
        def callback(monitor,_hdc,_rect,_data):
            info=MonitorInfo()
            info.cbSize=ctypes.sizeof(MonitorInfo)
            if self.user32.GetMonitorInfoW(monitor,ctypes.byref(info)):
                work=info.rcWork
                areas.append((work.left,work.top,work.right,work.bottom))
            return True
        self.user32.EnumDisplayMonitors(0,None,callback,0)
        return areas

    def virtual_bounds_and_ground(self,x:int,y:int)->tuple[int,int,int]:
        areas=self.monitor_work_areas()
        if not areas:
            left,_top,right,bottom=self.work_area()
            return left,right,bottom
        virtual_left=min(area[0] for area in areas)
        virtual_right=max(area[2] for area in areas)
        containing=[area for area in areas if area[0]<=x<area[2] and area[1]<=y<area[3]]
        if containing:
            selected=containing[0]
        else:
            selected=min(areas,key=lambda area:max(area[0]-x,0,x-area[2])**2+max(area[1]-y,0,y-area[3])**2)
        return virtual_left,virtual_right,selected[3]

    def area_for_rect(self,x:int,y:int,width:int,height:int)->tuple[int,int,int,int]:
        areas=self.monitor_work_areas()
        if not areas:
            return self.work_area()
        rect_right=x+max(1,width)
        rect_bottom=y+max(1,height)

        def overlap(area):
            overlap_w=max(0,min(rect_right,area[2])-max(x,area[0]))
            overlap_h=max(0,min(rect_bottom,area[3])-max(y,area[1]))
            return overlap_w*overlap_h

        best=max(areas,key=overlap)
        if overlap(best)>0:
            return best
        center_x=x+width//2
        center_y=y+height//2
        return min(areas,key=lambda area:
            max(area[0]-center_x,0,center_x-area[2])**2+
            max(area[1]-center_y,0,center_y-area[3])**2
        )

    def area_for_point(self,x:int,y:int)->tuple[int,int,int,int]:
        areas=self.monitor_work_areas()
        if not areas:
            return self.work_area()
        containing=[area for area in areas if area[0]<=x<area[2] and area[1]<=y<area[3]]
        if containing:
            return containing[0]
        return min(areas,key=lambda area:
            max(area[0]-x,0,x-area[2])**2+max(area[1]-y,0,y-area[3])**2
        )

    def set_window_position(self,hwnd:int,x:int,y:int)->bool:
        if not self.user32 or not hwnd:
            return False
        try:
            root_hwnd=self.user32.GetAncestor(wintypes.HWND(hwnd),2) or hwnd
            # SetWindowPos uses absolute virtual-screen coordinates, including negative X/Y.
            flags=0x0001 | 0x0004 | 0x0010  # NOSIZE | NOZORDER | NOACTIVATE
            return bool(self.user32.SetWindowPos(wintypes.HWND(root_hwnd),0,int(x),int(y),0,0,flags))
        except (AttributeError,OSError,ValueError):
            return False

    def force_topmost(self,hwnd:int)->bool:
        if not self.user32 or not hwnd:
            return False
        try:
            root_hwnd=self.user32.GetAncestor(wintypes.HWND(hwnd),2) or hwnd
            hwnd_topmost=wintypes.HWND(-1)
            flags=0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
            return bool(self.user32.SetWindowPos(
                wintypes.HWND(root_hwnd),hwnd_topmost,0,0,0,0,flags
            ))
        except (AttributeError,OSError,ValueError):
            return False

    def cursor_position(self)->tuple[int,int]:
        if not self.user32:
            return 0,0
        point=Point()
        self.user32.GetCursorPos(ctypes.byref(point))
        return point.x,point.y

    def area_nearest_x(self,x:int)->tuple[int,int,int,int]:
        areas=self.monitor_work_areas()
        if not areas:
            return self.work_area()
        matching=[area for area in areas if area[0]<=x<area[2]]
        if matching:
            return matching[0]
        return min(areas,key=lambda area:min(abs(x-area[0]),abs(x-area[2])))

    def adjacent_area(self,current:tuple[int,int,int,int],direction:int):
        areas=[area for area in self.monitor_work_areas() if area!=current]
        if not areas:
            return None

        current_center=(current[0]+current[2])/2
        if direction>0:
            candidates=[area for area in areas if (area[0]+area[2])/2>current_center]
        else:
            candidates=[area for area in areas if (area[0]+area[2])/2<current_center]
        if not candidates:
            return None

        def score(area):
            vertical_overlap=max(0,min(current[3],area[3])-max(current[1],area[1]))
            if direction>0:
                horizontal_gap=max(0,area[0]-current[2])
            else:
                horizontal_gap=max(0,current[0]-area[2])
            center_gap=abs((area[0]+area[2])/2-current_center)
            # Prefer the physically neighboring display, especially one sharing a vertical edge.
            return (0 if vertical_overlap>0 else 1,horizontal_gap,center_gap)

        return min(candidates,key=score)

    def direct_window_at_point(self,x:int,y:int)->int:
        if not self.user32:
            return 0
        hwnd=self.user32.WindowFromPoint(Point(x,y))
        if not hwnd:
            return 0
        hwnd=self.user32.GetAncestor(hwnd,2)
        class_name=ctypes.create_unicode_buffer(128)
        self.user32.GetClassNameW(hwnd,class_name,128)
        excluded={"Progman","WorkerW","Shell_TrayWnd","Shell_SecondaryTrayWnd"}
        if class_name.value in excluded:
            return 0
        return int(hwnd)

    def window_rect(self,hwnd:int)->tuple[int,int,int,int]|None:
        if not self.user32 or not hwnd or not self.user32.IsWindow(hwnd) or not self.user32.IsWindowVisible(hwnd):
            return None
        if self.user32.IsIconic(hwnd):
            return None
        rect=Rect()
        if not self.user32.GetWindowRect(hwnd,ctypes.byref(rect)):
            return None
        if rect.right-rect.left<150 or rect.bottom-rect.top<100:
            return None
        return rect.left,rect.top,rect.right,rect.bottom

    def visible_window_rect(self,hwnd:int)->tuple[int,int,int,int]|None:
        """Return the visible outer frame, avoiding the invisible resize border on Win10/11."""
        rect=self.window_rect(hwnd)
        if not rect or sys.platform!="win32":
            return rect
        try:
            dwmapi=ctypes.windll.dwmapi
            frame=Rect()
            # DWMWA_EXTENDED_FRAME_BOUNDS = 9
            result=dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),9,ctypes.byref(frame),ctypes.sizeof(frame)
            )
            if result==0 and frame.right>frame.left and frame.bottom>frame.top:
                return frame.left,frame.top,frame.right,frame.bottom
        except (AttributeError,OSError,ValueError):
            pass
        return rect

    def titlebar_ground(self,hwnd:int)->tuple[int,int,int]|None:
        """Return the horizontal top surface of an application window.

        Normally the pet's feet sit exactly on the app's visible top edge, so the
        pet looks like it is standing *on* the window.  A maximized window has no
        usable space above that edge; in that special case we move the surface a
        little way into the title/tab bar so the pet remains visible on screen.
        """
        rect=self.visible_window_rect(hwnd)
        if not rect:
            return None
        left,top,right,_bottom=rect
        area=self.area_for_rect(left,top,max(1,right-left),1)
        monitor_top=area[1]
        if top<=monitor_top+2:
            dpi=96
            try:
                get_dpi=getattr(self.user32,"GetDpiForWindow",None)
                if get_dpi:
                    dpi=int(get_dpi(wintypes.HWND(hwnd))) or 96
            except (AttributeError,OSError,ValueError):
                dpi=96
            bar_depth=max(28,min(44,round(36*dpi/96)))
            return left,right,top+bar_depth
        return left,right,top

    def falling_surface(self,x1:int,x2:int,old_foot_y:int,new_foot_y:int):
        """Find the first app top crossed by a falling pet.

        This is intentionally independent of the mouse drop point.  If the pet is
        released in the sky, every visible top-level app window under its feet is
        treated as a platform.
        """
        if not self.user32 or new_foot_y<old_foot_y:
            return None
        own_hwnd=int(self.user32.GetAncestor(wintypes.HWND(self.own_hwnd_getter()),2) or self.own_hwnd_getter())
        own_pid=wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(wintypes.HWND(own_hwnd),ctypes.byref(own_pid))
        hits=[]
        EnumProc=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)

        @EnumProc
        def callback(hwnd,_lparam):
            try:
                if not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd):
                    return True
                pid=wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value==own_pid.value:
                    return True
                class_name=ctypes.create_unicode_buffer(128)
                self.user32.GetClassNameW(hwnd,class_name,128)
                if class_name.value in {"Progman","WorkerW","Shell_TrayWnd","Shell_SecondaryTrayWnd"}:
                    return True
                rect=self.visible_window_rect(int(hwnd))
                if not rect:
                    return True
                left,top,right,bottom=rect
                if right<=x1 or left>=x2:
                    return True
                # Require a useful horizontal overlap, avoiding tiny edge catches.
                overlap=max(0,min(x2,right)-max(x1,left))
                if overlap<max(12,min(40,(x2-x1)//4)):
                    return True
                surface=self.titlebar_ground(int(hwnd))
                if not surface:
                    return True
                _sl,_sr,ground=surface
                if old_foot_y<=ground<=new_foot_y:
                    hits.append((ground,int(hwnd),surface))
            except (AttributeError,OSError,ValueError):
                pass
            return True

        self.user32.EnumWindows(callback,0)
        if not hits:
            return None
        return min(hits,key=lambda item:item[0])

class SetupWindow(tk.Toplevel):
    def __init__(self,master:tk.Tk,settings:Settings,first_run:bool=False):
        super().__init__(master)
        self.settings=settings
        self.result=False
        self.preview_frames=[]
        self.preview_index=0
        self.title("내 강아지 키우기")
        self.geometry("680x510")
        self.resizable(False,False)
        if not first_run:
            self.transient(master)
        self.name_var=tk.StringVar(value=settings.name)
        self.size_var=tk.IntVar(value=settings.size_percent)
        self.auto_var=tk.BooleanVar(value=settings.auto_start)
        left=ttk.Frame(self,padding=25)
        left.pack(side="left",fill="y")
        right=ttk.Frame(self,padding=25)
        right.pack(side="right",fill="both",expand=True)
        ttk.Label(left,text="내 강아지",font=("Malgun Gothic",20,"bold")).pack(anchor="w",pady=(0,25))
        ttk.Label(left,text="이름").pack(anchor="w")
        ttk.Entry(left,textvariable=self.name_var,width=26).pack(anchor="w",pady=(5,20))
        ttk.Label(left,text="크기").pack(anchor="w")
        self.size_text=ttk.Label(left,text=f"{settings.size_percent}%")
        self.size_text.pack(anchor="e")
        ttk.Scale(left,from_=10,to=180,variable=self.size_var,length=210,command=self._size_changed).pack()
        ttk.Label(left,text="10%                              180%",foreground="#777").pack(anchor="w")
        ttk.Checkbutton(left,text="Windows 시작 시 자동 실행",variable=self.auto_var).pack(anchor="w",pady=(25,30))
        row=ttk.Frame(left)
        row.pack(fill="x")
        if not first_run:
            ttk.Button(row,text="취소",command=self.destroy).pack(side="right",padx=(8,0))
        ttk.Button(row,text="저장",command=self._save).pack(side="right")
        ttk.Label(right,text="미리보기",font=("Malgun Gothic",13,"bold")).pack()
        self.preview=tk.Canvas(right,width=330,height=350,bg="#f4f0f5",highlightthickness=0)
        self.preview.pack(pady=12)
        self._load_preview()
        self._animate_preview()
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def _size_changed(self,_value=None):
        value=int(round(self.size_var.get()/5)*5)
        self.size_var.set(value)
        self.size_text.configure(text=f"{value}%")
        self._load_preview()

    def _load_preview(self):
        self.preview_frames.clear()
        size=max(1,int(155*self.size_var.get()/100))
        for col in range(4):
            image=Image.open(resource_path(f"assets/front/2_{col}.png")).convert("RGBA")
            image=resize_sprite(image,size)
            self.preview_frames.append(ImageTk.PhotoImage(image))

    def _animate_preview(self):
        if self.winfo_exists() and self.preview_frames:
            self.preview.delete("dog")
            frame=self.preview_frames[self.preview_index%len(self.preview_frames)]
            self.preview.create_image(165,180,image=frame,anchor="center",tags="dog")
            self.preview_index+=1
            self.after(180,self._animate_preview)

    def _save(self):
        if not self.name_var.get().strip():
            messagebox.showwarning("이름 확인","강아지 이름을 입력해 주세요.",parent=self)
            return
        previous_auto_start=self.settings.auto_start
        requested_auto_start=self.auto_var.get()
        self.settings.configured=True
        self.settings.name=self.name_var.get().strip()
        self.settings.size_percent=max(10,min(180,self.size_var.get()))
        self.settings.auto_start=requested_auto_start
        self.settings.save()
        # 자동 실행 설정이 실제로 바뀐 경우에만 Windows Run 레지스트리에 접근한다.
        # 설정을 그대로 저장하거나 최초 실행 시 꺼져 있으면 레지스트리를 열지 않는다.
        if requested_auto_start!=previous_auto_start:
            set_auto_start(requested_auto_start)
        self.result=True
        self.destroy()


class StatusWindow(tk.Toplevel):
    def __init__(self,master:tk.Tk,settings:Settings):
        super().__init__(master)
        self.settings=settings
        self.title(f"{settings.name}의 상태")
        self.geometry("430x390")
        self.resizable(False,False)
        self.transient(master)
        self.frame=ttk.Frame(self,padding=20)
        self.frame.pack(fill="both",expand=True)
        ttk.Label(self.frame,text=f"🐶 {settings.name}의 현재 상태",font=("Malgun Gothic",17,"bold")).pack(anchor="w",pady=(0,14))
        self.rows={}
        for key,label in [("affection","💕 애정도"),("hunger","🍖 포만감"),("energy","⚡ 체력"),("mood","😊 기분")]:
            row=ttk.Frame(self.frame)
            row.pack(fill="x",pady=6)
            ttk.Label(row,text=label,width=11).pack(side="left")
            bar=ttk.Progressbar(row,maximum=100,length=230)
            bar.pack(side="left",padx=(4,8))
            value=ttk.Label(row,width=5,anchor="e")
            value.pack(side="left")
            self.rows[key]=(bar,value)
        ttk.Separator(self.frame).pack(fill="x",pady=14)
        self.level_label=ttk.Label(self.frame,font=("Malgun Gothic",11,"bold"))
        self.level_label.pack(anchor="w")
        self.exp_bar=ttk.Progressbar(self.frame,maximum=100,length=350)
        self.exp_bar.pack(anchor="w",pady=(7,3))
        self.exp_label=ttk.Label(self.frame,foreground="#666")
        self.exp_label.pack(anchor="w")
        ttk.Button(self.frame,text="닫기",command=self.destroy).pack(anchor="e",pady=(18,0))
        self.refresh()
        self.update_idletasks()
        self.lift()
        self.focus_force()

    def refresh(self):
        if not self.winfo_exists():
            return
        for key,(bar,label) in self.rows.items():
            value=max(0,min(100,int(getattr(self.settings,key))))
            bar["value"]=value
            label.configure(text=f"{value}%")
        needed=max(20,self.settings.level*35)
        exp=max(0,int(self.settings.exp))
        self.level_label.configure(text=f"⭐ 레벨 {self.settings.level}")
        self.exp_bar["maximum"]=needed
        self.exp_bar["value"]=min(exp,needed)
        self.exp_label.configure(text=f"경험치 {exp} / {needed}")
        self.after(700,self.refresh)

class CollectionWindow(tk.Toplevel):
    def __init__(self,master:tk.Tk,settings:Settings):
        super().__init__(master)
        self.title(f"{settings.name}의 수집품 / 모험 통계")
        self.geometry("700x460")
        self.resizable(True,True)
        self.transient(master)
        frame=ttk.Frame(self,padding=18)
        frame.pack(fill="both",expand=True)
        ttk.Label(frame,text="수집품 / 모험 통계",font=("Malgun Gothic",17,"bold")).pack(anchor="w")
        status=f"모험 {settings.adventures}회 · 다툼 {settings.fights}회 · 승리 {settings.wins}회"
        ttk.Label(frame,text=status,foreground="#666").pack(anchor="w",pady=(4,12))

        tree=ttk.Treeview(frame,columns=("item","rarity","chance","count"),show="headings",height=13)
        tree.heading("item",text="발견한 물건")
        tree.heading("rarity",text="등급")
        tree.heading("chance",text="발견 확률")
        tree.heading("count",text="개수")
        tree.column("item",width=300,anchor="w")
        tree.column("rarity",width=90,anchor="center")
        tree.column("chance",width=110,anchor="center")
        tree.column("count",width=80,anchor="center")
        tree.pack(fill="both",expand=True)
        for name,icon in COLLECTIBLES.items():
            rarity,chance=collectible_rarity_and_chance(name)
            count=settings.collection.get(name,0)
            display_name=f"{icon} {name}" if count>0 else "❔ ???"
            tree.insert("","end",values=(display_name,rarity,chance,count))

        ttk.Button(frame,text="닫기",command=self.destroy).pack(anchor="e",pady=(12,0))
        self.update_idletasks()
        self.lift()
        self.focus_force()

class AdventureLogWindow(tk.Toplevel):
    def __init__(self,master:tk.Tk,settings:Settings):
        super().__init__(master)
        self.title(f"{settings.name}의 오늘의 모험 기록")
        self.geometry("680x460")
        self.minsize(520,320)
        self.transient(master)
        frame=ttk.Frame(self,padding=18)
        frame.pack(fill="both",expand=True)
        ttk.Label(frame,text="📖 오늘의 모험 기록",font=("Malgun Gothic",17,"bold")).pack(anchor="w")
        ttk.Label(
            frame,text=f"{settings.adventure_log_date} · 최근 {len(settings.adventure_log)}개 (최대 200개)",
            foreground="#666"
        ).pack(anchor="w",pady=(4,12))

        tree=ttk.Treeview(frame,columns=("time","kind","detail"),show="headings",height=14)
        tree.heading("time",text="시간")
        tree.heading("kind",text="종류")
        tree.heading("detail",text="기록")
        tree.column("time",width=90,anchor="center",stretch=False)
        tree.column("kind",width=90,anchor="center",stretch=False)
        tree.column("detail",width=430,anchor="w")
        scrollbar=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y")
        tree.pack(fill="both",expand=True)
        for entry in reversed(settings.adventure_log):
            tree.insert("","end",values=(entry.get("time",""),entry.get("kind",""),entry.get("detail","")))

        if not settings.adventure_log:
            tree.insert("","end",values=("-","-","아직 오늘의 모험 기록이 없어요."))
        ttk.Button(frame,text="닫기",command=self.destroy).pack(anchor="e",pady=(12,0))
        self.update_idletasks()
        self.lift()
        self.focus_force()

class PetInfoWindow(tk.Toplevel):
    def __init__(self,master:tk.Tk,settings:Settings,initial_tab:str="status"):
        super().__init__(master)
        self.settings=settings
        self.title(f"{settings.name} 정보")
        self.geometry("740x530")
        self.minsize(620,440)
        self.transient(master)

        outer=ttk.Frame(self,padding=16)
        outer.pack(fill="both",expand=True)
        self.notebook=ttk.Notebook(outer)
        self.notebook.pack(fill="both",expand=True)

        self.status_tab=ttk.Frame(self.notebook,padding=22)
        self.collection_tab=ttk.Frame(self.notebook,padding=16)
        self.log_tab=ttk.Frame(self.notebook,padding=16)
        self.notebook.add(self.status_tab,text="현재 상태")
        self.notebook.add(self.collection_tab,text="수집품 / 모험 통계")
        self.notebook.add(self.log_tab,text="오늘의 모험 기록")

        self._build_status_tab()
        self._build_collection_tab()
        self._build_log_tab()
        tabs={"status":self.status_tab,"collection":self.collection_tab,"log":self.log_tab}
        self.notebook.select(tabs.get(initial_tab,self.status_tab))

        ttk.Button(outer,text="닫기",command=self.destroy).pack(anchor="e",pady=(12,0))
        self.update_idletasks()
        self.lift()
        self.focus_force()
        self._refresh_status()

    def _build_status_tab(self):
        ttk.Label(
            self.status_tab,text=f"🐶 {self.settings.name}의 현재 상태",
            font=("Malgun Gothic",17,"bold")
        ).pack(anchor="w",pady=(0,14))
        self.status_rows={}
        for key,label in [("affection","💕 애정도"),("hunger","🍖 포만감"),("energy","⚡ 체력"),("mood","😊 기분")]:
            row=ttk.Frame(self.status_tab)
            row.pack(fill="x",pady=7)
            ttk.Label(row,text=label,width=12).pack(side="left")
            bar=ttk.Progressbar(row,maximum=100,length=360)
            bar.pack(side="left",padx=(4,10),fill="x",expand=True)
            value=ttk.Label(row,width=6,anchor="e")
            value.pack(side="left")
            self.status_rows[key]=(bar,value)
        ttk.Separator(self.status_tab).pack(fill="x",pady=16)
        self.level_label=ttk.Label(self.status_tab,font=("Malgun Gothic",11,"bold"))
        self.level_label.pack(anchor="w")
        self.exp_bar=ttk.Progressbar(self.status_tab,maximum=100,length=480)
        self.exp_bar.pack(anchor="w",fill="x",pady=(8,4))
        self.exp_label=ttk.Label(self.status_tab,foreground="#666")
        self.exp_label.pack(anchor="w")

    def _build_collection_tab(self):
        status=f"모험 {self.settings.adventures}회 · 다툼 {self.settings.fights}회 · 승리 {self.settings.wins}회"
        ttk.Label(self.collection_tab,text=status,foreground="#666").pack(anchor="w",pady=(0,10))
        tree_frame=ttk.Frame(self.collection_tab)
        tree_frame.pack(fill="both",expand=True)
        tree=ttk.Treeview(tree_frame,columns=("item","rarity","chance","count"),show="headings",height=14)
        for column,title in [("item","발견한 물건"),("rarity","등급"),("chance","발견 확률"),("count","개수")]:
            tree.heading(column,text=title)
        tree.column("item",width=300,anchor="w")
        tree.column("rarity",width=90,anchor="center")
        tree.column("chance",width=110,anchor="center")
        tree.column("count",width=80,anchor="center")
        scrollbar=ttk.Scrollbar(tree_frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y")
        tree.pack(fill="both",expand=True)
        for name,icon in COLLECTIBLES.items():
            rarity,chance=collectible_rarity_and_chance(name)
            count=self.settings.collection.get(name,0)
            display_name=f"{icon} {name}" if count>0 else "❔ ???"
            tree.insert("","end",values=(display_name,rarity,chance,count))

    def _build_log_tab(self):
        ttk.Label(
            self.log_tab,
            text=f"{self.settings.adventure_log_date} · 최근 {len(self.settings.adventure_log)}개 (최대 200개)",
            foreground="#666"
        ).pack(anchor="w",pady=(0,10))
        tree_frame=ttk.Frame(self.log_tab)
        tree_frame.pack(fill="both",expand=True)
        tree=ttk.Treeview(tree_frame,columns=("time","kind","detail"),show="headings",height=14)
        tree.heading("time",text="시간")
        tree.heading("kind",text="종류")
        tree.heading("detail",text="기록")
        tree.column("time",width=90,anchor="center",stretch=False)
        tree.column("kind",width=90,anchor="center",stretch=False)
        tree.column("detail",width=430,anchor="w")
        scrollbar=ttk.Scrollbar(tree_frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y")
        tree.pack(fill="both",expand=True)
        for entry in reversed(self.settings.adventure_log):
            tree.insert("","end",values=(entry.get("time",""),entry.get("kind",""),entry.get("detail","")))
        if not self.settings.adventure_log:
            tree.insert("","end",values=("-","-","아직 오늘의 모험 기록이 없어요."))

    def _refresh_status(self):
        if not self.winfo_exists():
            return
        for key,(bar,label) in self.status_rows.items():
            value=max(0,min(100,int(getattr(self.settings,key))))
            bar["value"]=value
            label.configure(text=f"{value}%")
        needed=max(20,self.settings.level*35)
        exp=max(0,int(self.settings.exp))
        self.level_label.configure(text=f"⭐ 레벨 {self.settings.level}")
        self.exp_bar["maximum"]=needed
        self.exp_bar["value"]=min(exp,needed)
        self.exp_label.configure(text=f"경험치 {exp} / {needed}")
        self.after(700,self._refresh_status)

class DogWindow:
    def __init__(self,root:tk.Tk,settings:Settings):
        self.root=root
        self.settings=settings
        self.tick=0
        self.frame_index=0
        self.state="front"
        self.state_until=45
        self.direction=random.choice((-1,1))
        self.drag_origin=None
        self.position_origin=None
        self.falling=False
        self.fall_velocity=0.0
        self.bounce_count=0
        self.bubble_until=0
        self.message=""
        self.found_icon=""
        self.icon_until=0
        self.ball_until=0
        self.sleeping=False
        self.sleep_end_at=0.0
        self.last_sleep_recovery=0.0
        self.next_rest_at=time.monotonic()+random.randint(30,60)
        self.next_adventure_at=time.monotonic()+random.randint(180,300)
        self.next_bark_at=time.monotonic()+random.randint(35,90)
        self.last_status_update=time.monotonic()
        self.frames={}
        self.flipped={}
        root.overrideredirect(True)
        root.attributes("-topmost",True)
        root.configure(bg=TRANSPARENT)
        try:
            root.wm_attributes("-transparentcolor",TRANSPARENT)
        except tk.TclError:
            pass
        self.canvas=tk.Canvas(root,bg=TRANSPARENT,highlightthickness=0)
        self.canvas.pack()
        self.bubble_win=tk.Toplevel(root)
        self.bubble_win.overrideredirect(True)
        self.bubble_win.attributes("-topmost",True)
        self.bubble_win.configure(bg=TRANSPARENT)
        try:
            self.bubble_win.wm_attributes("-transparentcolor",TRANSPARENT)
        except tk.TclError:
            pass
        self.bubble_canvas=tk.Canvas(self.bubble_win,bg=TRANSPARENT,highlightthickness=0)
        self.bubble_canvas.pack()
        self.bubble_win.withdraw()
        self.canvas.bind("<ButtonPress-1>",self._drag_start)
        self.canvas.bind("<B1-Motion>",self._drag_move)
        self.canvas.bind("<ButtonRelease-1>",self._drag_end)
        self.canvas.bind("<Double-Button-1>",lambda _event:self.happy())
        self.canvas.bind("<Button-3>",self._show_menu)
        self.menu=tk.Menu(root,tearoff=False)
        self.menu.add_command(label="❤️ 현재 상태",command=self.show_status)
        self.menu.add_separator()
        self.menu.add_command(label="🍖 밥 주기",command=self.feed)
        self.menu.add_command(label="🎾 공놀이",command=self.play)
        self.menu.add_command(label="💕 쓰다듬기",command=self.happy)
        self.menu.add_command(label="💤 잠자기",command=self.sleep)
        self.stay_sitting_var=tk.BooleanVar(value=self.settings.stay_sitting)
        self.menu.add_checkbutton(
            label="🪑 가만히 앉아있기",variable=self.stay_sitting_var,
            command=self.toggle_stay_sitting
        )
        self.speech_bubble_var=tk.BooleanVar(value=self.settings.show_speech_bubbles)
        self.menu.add_checkbutton(
            label="💬 말풍선 표시",variable=self.speech_bubble_var,
            command=self.toggle_speech_bubbles
        )
        self.follow_mouse_var=tk.BooleanVar(value=self.settings.follow_mouse)
        self.menu.add_checkbutton(
            label="🖱 마우스 따라다니기",variable=self.follow_mouse_var,
            command=self.toggle_follow_mouse
        )
        self.menu.add_separator()
        self.menu.add_command(label="🎒 수집품 / 모험 통계",command=self.show_collection)
        self.menu.add_command(label="📖 오늘의 모험 기록",command=self.show_adventure_log)
        self.menu.add_command(label="⬇ 작업 표시줄로 내려가기",command=self.go_taskbar)
        self.menu.add_separator()
        self.menu.add_command(label="🔄 펫 초기화",command=self.reset_pet)
        self.menu.add_command(label="설정",command=self.open_setup)
        self.menu.add_separator()
        self.menu.add_command(label="종료",command=self.close)
        root.update_idletasks()
        self.surface=WindowsSurface(lambda:root.winfo_id())
        self.surface_hwnd=0
        self.settings.surface_hwnd=0
        self.settings.surface_offset_y=0
        self._ensure_daily_log()
        self._load_frames()
        self._snap_to_surface(initial=True)
        self.say(f"안녕! 나는 {settings.name}야.",2800)
        self._keep_windows_on_top()
        self.animate()

    def _keep_windows_on_top(self):
        try:
            self.root.attributes("-topmost",True)
            self.surface.force_topmost(self.root.winfo_id())
            if self.bubble_win.winfo_viewable():
                self.bubble_win.attributes("-topmost",True)
                self.surface.force_topmost(self.bubble_win.winfo_id())
            self.root.after(1000,self._keep_windows_on_top)
        except tk.TclError:
            pass

    def _load_frames(self):
        self.frames.clear()
        self.flipped.clear()
        max_size=max(1,int(170*self.settings.size_percent/100))
        for state,row in {**SIDE_STATES,**FRONT_STATES}.items():
            folder="side" if state in SIDE_STATES else "front"
            normal=[]
            reverse=[]
            for col in range(4):
                image=Image.open(resource_path(f"assets/{folder}/{row}_{col}.png")).convert("RGBA")
                image=resize_sprite(image,max_size)
                normal.append(ImageTk.PhotoImage(image))
                reverse.append(ImageTk.PhotoImage(image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)))
            self.frames[state]=normal
            self.flipped[state]=reverse
        sizes=[(photo.width(),photo.height()) for frames in self.frames.values() for photo in frames]
        self.dog_width=max(width for width,_ in sizes)
        self.dog_height=max(height for _,height in sizes)
        self.width=max(18,self.dog_width+4)
        self.height=self.dog_height+34
        self.canvas.configure(width=self.width,height=self.height)
        self.root.geometry(f"{self.width}x{self.height}")

    def _surface_bounds(self):
        if self.surface_hwnd:
            titlebar=self.surface.titlebar_ground(self.surface_hwnd)
            if titlebar:
                return titlebar
            self.surface_hwnd=0
            self.settings.surface_hwnd=0
            self.settings.save()
        center_x=self.root.winfo_x()+self.width//2
        center_y=self.root.winfo_y()+self.height//2
        return self.surface.virtual_bounds_and_ground(center_x,center_y)

    def _place(self,x:int,y:int):
        x=int(x)
        y=int(y)
        # Tk interprets a negative geometry offset as a distance from the right/bottom edge.
        # That prevents reliable placement on monitors whose virtual coordinates are negative.
        if sys.platform=="win32" and self.surface.set_window_position(self.root.winfo_id(),x,y):
            return
        self.root.geometry(f"{x:+d}{y:+d}")

    def _snap_to_surface(self,initial=False):
        if self.surface_hwnd:
            left,right,ground=self._surface_bounds()
            x=self.settings.x if initial and left<=self.settings.x<=right-self.width else self.root.winfo_x()
            x=max(left,min(right-self.width,x))
            self._place(x,ground-self.height)
            return

        x=self.settings.x if initial and self.settings.x!=-1 else self.root.winfo_x()
        current_y=self.root.winfo_y()
        area=self.surface.area_for_rect(x,current_y,self.width,self.height)
        left,_top,right,ground=area
        x=max(left,min(right-self.width,x))
        self._place(x,ground-self.height)

    def animate(self):
        self.tick+=1
        self._ensure_daily_log()
        self._update_needs()
        if self.sleeping:
            self._update_sleep()
        elif not self.settings.stay_sitting:
            self._maybe_adventure()
            self._maybe_bark()
            self._maybe_rest()
        if self.drag_origin is None and not self.sleeping:
            if self.falling:
                self._apply_gravity()
            elif self.settings.stay_sitting:
                self._hold_sitting()
            elif self.settings.follow_mouse:
                self._follow_mouse()
            else:
                self._advance_state()
                self._move_on_surface()
        self.canvas.delete("all")
        if self.tick<self.bubble_until:
            self._draw_bubble()
        else:
            self.bubble_win.withdraw()
        frames=self.frames[self.state] if self.direction>0 else self.flipped[self.state]
        if self.state=="sit" and self.settings.stay_sitting and not self.sleeping:
            # "가만히 앉아있기"는 front/1_0.png와 1_1.png만 반복한다.
            frames=frames[:2]
        frame=frames[self.frame_index%len(frames)]
        self.canvas.create_image(self.width/2,self.height-3,image=frame,anchor="s")
        if self.tick<self.ball_until:
            phase=(self.tick%24)/24*math.tau
            ball_x=self.width/2+math.sin(phase)*max(18,self.width*0.28)
            ball_y=self.height-18-abs(math.sin(phase))*30
            self.canvas.create_text(ball_x,ball_y,text="🎾",font=("Segoe UI Emoji",18))
        if self.sleeping:
            float_y=4+int((math.sin(self.tick/4)+1)*3)
            self.canvas.create_text(self.width-10,float_y,text="Zzz",font=("Malgun Gothic",11,"bold"),fill="#7165a8",anchor="ne")
        if self.tick<self.icon_until and self.found_icon:
            self.canvas.create_text(self.width-10,28,text=self.found_icon,font=("Segoe UI Emoji",14),anchor="ne")
        self.frame_index+=1
        if self.tick%160==0:
            self._save_position()
        delay=45 if self.falling else 120 if self.state=="run" else 170
        self.root.after(delay,self.animate)


    def _update_needs(self):
        now=time.monotonic()
        elapsed=now-self.last_status_update
        if elapsed<20:
            return
        steps=int(elapsed//20)
        self.last_status_update+=steps*20
        old=(self.settings.hunger,self.settings.energy,self.settings.mood)
        self.settings.hunger=max(0,self.settings.hunger-steps)
        if self.state in ("walk","run"):
            self.settings.energy=max(0,self.settings.energy-steps)
        elif self.state in ("sit","front"):
            self.settings.energy=min(100,self.settings.energy+steps)
        if self.settings.hunger<25 or self.settings.energy<20:
            self.settings.mood=max(0,self.settings.mood-steps)
        elif self.settings.hunger>60 and self.settings.energy>50:
            self.settings.mood=min(100,self.settings.mood+max(1,steps//2))
        if old!=(self.settings.hunger,self.settings.energy,self.settings.mood):
            self.settings.save()

    def _gain_exp(self,amount:int):
        self.settings.exp=max(0,self.settings.exp+amount)
        leveled=False
        while self.settings.exp>=max(20,self.settings.level*35):
            needed=max(20,self.settings.level*35)
            self.settings.exp-=needed
            self.settings.level+=1
            leveled=True
        if leveled:
            self.say(f"레벨 {self.settings.level}! 더 씩씩해졌어! ⭐",2600)

    def _apply_gravity(self):
        # While falling, applications are real platforms.  We inspect the vertical
        # sweep of the pet's feet before falling all the way to the taskbar.
        self.surface_hwnd=0
        left,right,desktop_ground=self._surface_bounds()
        desktop_target_y=desktop_ground-self.height
        x=max(left,min(right-self.width,self.root.winfo_x()))
        y=self.root.winfo_y()
        old_foot=y+self.height
        self.fall_velocity+=2.8
        next_y=y+round(self.fall_velocity)
        next_foot=next_y+self.height

        hit=self.surface.falling_surface(x,x+self.width,old_foot,next_foot)
        if hit:
            ground,hwnd,surface=hit
            sl,sr,_=surface
            self.surface_hwnd=hwnd
            self.settings.surface_hwnd=hwnd
            self.settings.surface_offset_y=0
            x=max(sl,min(sr-self.width,x))
            next_y=ground-self.height
            self.falling=False
            self.fall_velocity=0.0
            self.bounce_count=0
            self._set_state("happy",18)
            self.say("착지!",1500)
            self._place(x,next_y)
            self._save_position()
            return

        if next_y>=desktop_target_y:
            next_y=desktop_target_y
            if self.bounce_count==0 and self.fall_velocity>8:
                self.bounce_count=1
                self.fall_velocity=-max(5.0,min(12.0,self.fall_velocity*0.32))
            else:
                self.falling=False
                self.fall_velocity=0.0
                self.bounce_count=0
                self._set_state("happy",18)
                self.say("착지!",1300)
                self._save_position()
        self._place(x,next_y)

    def _advance_state(self):
        if self.tick<self.state_until:
            return
        previous=self.state
        if previous=="run":
            self._set_state("pant",random.randint(20,35))
        elif previous in ("pant","happy","sit","front"):
            self._set_state(random.choice(["idle","walk","walk"]),random.randint(25,60))
        else:
            self._set_state(random.choice(["front","sit","walk","run"]),random.randint(25,65))
            if random.random()<0.4:
                self.direction*=-1

    def _maybe_rest(self):
        now=time.monotonic()
        if self.settings.follow_mouse or now<self.next_rest_at or self.falling or self.drag_origin:
            return
        if self.tick<self.ball_until:
            self.next_rest_at=now+15
            return
        self.next_rest_at=now+random.randint(60,120)
        self._set_state("sit",random.randint(90,175))

    def _hold_sitting(self):
        if self.state!="sit":
            self._set_state("sit",10**6)
        self._snap_to_surface()

    def _set_state(self,state,duration):
        self.state=state
        self.state_until=self.tick+duration
        self.frame_index=0

    def _move_on_surface(self):
        if self.state not in ("walk","run"):
            self._snap_to_surface()
            return
        speed=7 if self.state=="run" else 3
        if self.surface_hwnd:
            left,right,ground=self._surface_bounds()
            x=self.root.winfo_x()+speed*self.direction
            if x<=left or x>=right-self.width:
                self.direction*=-1
                x=max(left,min(right-self.width,x))
            self._place(x,ground-self.height)
            return
        current=self.surface.area_for_rect(self.root.winfo_x(),self.root.winfo_y(),self.width,self.height)
        x=self.root.winfo_x()+speed*self.direction
        ground=current[3]
        if self.direction>0 and x+self.width>=current[2]:
            adjacent=self.surface.adjacent_area(current,1)
            if adjacent:
                x=adjacent[0]+1
                ground=adjacent[3]
            else:
                self.direction=-1
                x=current[2]-self.width
        elif self.direction<0 and x<=current[0]:
            adjacent=self.surface.adjacent_area(current,-1)
            if adjacent:
                x=adjacent[2]-self.width-1
                ground=adjacent[3]
            else:
                self.direction=1
                x=current[0]
        self._place(x,ground-self.height)

    def _follow_mouse(self):
        cursor_x,cursor_y=self.surface.cursor_position()
        target_area=self.surface.area_for_point(cursor_x,cursor_y)
        current_x=self.root.winfo_x()
        current_y=self.root.winfo_y()
        current_area=self.surface.area_for_rect(current_x,current_y,self.width,self.height)
        target_x=max(target_area[0],min(target_area[2]-self.width,cursor_x-self.width//2))
        distance=target_x-current_x

        # A vertically arranged monitor can share the same X range. In that case,
        # switch floors directly so the pet can still reach the cursor's monitor.
        horizontal_overlap=max(current_area[0],target_area[0])<min(current_area[2],target_area[2])
        if current_area!=target_area and horizontal_overlap and abs(distance)<70:
            current_x=target_x
            current_area=target_area
            distance=0

        if current_area==target_area and abs(distance)<=65:
            if self.state!="sit":
                self._set_state("sit",10**6)
            self._place(current_x,target_area[3]-self.height)
            return

        target_center=(target_area[0]+target_area[2])//2
        dog_center=current_x+self.width//2
        self.direction=1 if (distance>0 if current_area==target_area else target_center>dog_center) else -1
        travel_distance=abs(distance) if current_area==target_area else abs(target_center-dog_center)
        next_state="run" if travel_distance>350 else "walk"
        if self.state!=next_state:
            self._set_state(next_state,10**6)
        speed=8 if next_state=="run" else 4
        x=current_x+speed*self.direction

        virtual_left=min(area[0] for area in self.surface.monitor_work_areas())
        virtual_right=max(area[2] for area in self.surface.monitor_work_areas())
        x=max(virtual_left,min(virtual_right-self.width,x))
        center=x+self.width//2
        ground=target_area[3] if target_area[0]<=center<target_area[2] else current_area[3]
        self._place(x,ground-self.height)

    def _draw_bubble(self):
        if not self.message:
            self.bubble_win.withdraw()
            return

        # The speech bubble is a separate window so long text is not limited
        # by the dog's sprite width. Tk measures the wrapped text first, then
        # the bubble grows vertically as needed.
        max_text_width=280
        min_text_width=90
        padding_x=14
        padding_y=9
        tail_h=9

        self.bubble_canvas.delete("all")
        text_id=self.bubble_canvas.create_text(
            0,0,text=self.message,width=max_text_width,anchor="nw",
            font=("Malgun Gothic",9),fill="#332d37",justify="center"
        )
        bbox=self.bubble_canvas.bbox(text_id) or (0,0,min_text_width,18)
        text_w=max(min_text_width,min(max_text_width,bbox[2]-bbox[0]))
        text_h=max(18,bbox[3]-bbox[1])
        bubble_w=text_w+padding_x*2
        bubble_h=text_h+padding_y*2
        total_h=bubble_h+tail_h

        self.bubble_canvas.configure(width=bubble_w,height=total_h)
        self.bubble_canvas.delete("all")
        self.bubble_canvas.create_rectangle(
            1,1,bubble_w-2,bubble_h-1,fill="white",outline="#d8cedd",width=1
        )
        center=bubble_w/2
        self.bubble_canvas.create_polygon(
            center-6,bubble_h-1,center+6,bubble_h-1,center,bubble_h+tail_h-1,
            fill="white",outline="#d8cedd"
        )
        self.bubble_canvas.create_text(
            center,bubble_h/2,text=self.message,width=max_text_width,
            font=("Malgun Gothic",9),fill="#332d37",justify="center"
        )

        dog_x=self.root.winfo_x()
        dog_y=self.root.winfo_y()
        x=dog_x+(self.width-bubble_w)//2
        y=dog_y-total_h+13
        self.bubble_win.geometry(f"{bubble_w}x{total_h}")
        self.bubble_win.deiconify()
        self.bubble_win.update_idletasks()
        if sys.platform=="win32" and self.surface.set_window_position(self.bubble_win.winfo_id(),x,y):
            pass
        else:
            self.bubble_win.geometry(f"{x:+d}{y:+d}")
        self.bubble_win.lift()

    def say(self,message,milliseconds=2200):
        if not self.settings.show_speech_bubbles:
            self.message=""
            self.bubble_until=0
            self.bubble_win.withdraw()
            return
        self.message=message
        self.bubble_until=self.tick+max(1,milliseconds//150)

    def toggle_speech_bubbles(self):
        self.settings.show_speech_bubbles=bool(self.speech_bubble_var.get())
        if not self.settings.show_speech_bubbles:
            self.message=""
            self.bubble_until=0
            self.bubble_win.withdraw()
        self.settings.save()

    def toggle_follow_mouse(self):
        self._wake_from_sleep()
        self.settings.follow_mouse=bool(self.follow_mouse_var.get())
        if self.settings.follow_mouse and self.settings.stay_sitting:
            self.settings.stay_sitting=False
            self.stay_sitting_var.set(False)
        self.surface_hwnd=0
        self.settings.surface_hwnd=0
        self.settings.surface_offset_y=0
        if self.settings.follow_mouse:
            self._set_state("walk",10**6)
            self.say("마우스를 따라갈게! 🐾",1700)
        else:
            self._set_state("idle",random.randint(20,45))
            self.say("여기서 놀게!",1500)
        self.settings.save()

    def toggle_stay_sitting(self):
        self.settings.stay_sitting=bool(self.stay_sitting_var.get())
        if self.settings.stay_sitting:
            self.settings.follow_mouse=False
            self.follow_mouse_var.set(False)
            self._set_state("sit",10**6)
            self._snap_to_surface()
            self.say("여기 앉아 있을게!",1500)
        else:
            self._set_state("idle",random.randint(20,45))
            self.next_rest_at=time.monotonic()+random.randint(30,60)
            self.say("다시 놀아볼까?",1500)
        self.settings.save()

    def _wake_from_sleep(self):
        if not self.sleeping:
            return False
        self.sleeping=False
        self.sleep_end_at=0.0
        self._set_state("happy",18)
        return True

    def sleep(self):
        if self.sleeping:
            self._wake_from_sleep()
            self.say("잘 잤다!",1500)
            return
        self.sleeping=True
        now=time.monotonic()
        self.sleep_end_at=now+60
        self.last_sleep_recovery=now
        self.ball_until=0
        self._set_state("sit",10**6)
        self.say("조금 잘게... 💤",1500)

    def _update_sleep(self):
        now=time.monotonic()
        recovery_steps=int((now-self.last_sleep_recovery)//5)
        if recovery_steps>0:
            self.last_sleep_recovery+=recovery_steps*5
            self.settings.energy=min(100,self.settings.energy+recovery_steps*3)
            self.settings.mood=min(100,self.settings.mood+recovery_steps)
            self.settings.save()
        if now>=self.sleep_end_at or self.settings.energy>=100:
            self._wake_from_sleep()
            self.say("푹 잤다! 에너지가 생겼어!",1900)

    def _ensure_daily_log(self):
        today=datetime.now().date().isoformat()
        if self.settings.adventure_log_date!=today:
            self.settings.adventure_log_date=today
            self.settings.adventure_log=[]
            self.settings.save()

    def _add_adventure_log(self,kind:str,detail:str):
        self._ensure_daily_log()
        self.settings.adventure_log.append({
            "time":datetime.now().strftime("%H:%M:%S"),
            "kind":kind,
            "detail":detail,
        })
        self.settings.adventure_log=self.settings.adventure_log[-200:]

    @staticmethod
    def _choose_collectible()->tuple[str,str]:
        rarity_roll=random.random()
        if rarity_roll<0.001:
            pool=ULTRA_RARE_COLLECTIBLES
        elif rarity_roll<0.012:
            pool=RARE_COLLECTIBLES
        else:
            pool=COMMON_COLLECTIBLES
        item=random.choice(list(pool))
        return item,pool[item]

    def _maybe_bark(self):
        now=time.monotonic()
        if now<self.next_bark_at:
            return
        if self.drag_origin or self.falling or self.tick<self.bubble_until:
            self.next_bark_at=now+8
            return
        self.next_bark_at=now+random.randint(45,120)
        self._set_state("happy",random.randint(12,20))
        self.say(random.choice(["멍멍!", "왈왈!", "멍! 🐾"]),random.randint(1200,1900))

    def _maybe_adventure(self):
        if time.monotonic()<self.next_adventure_at or self.drag_origin or self.falling:
            return
        if self.state not in ("walk","run"):
            self.next_adventure_at=time.monotonic()+5
            return
        self.next_adventure_at=time.monotonic()+random.randint(180,300)
        self.settings.adventures+=1
        self._gain_exp(5)
        if random.random()<0.76:
            item,item_icon=self._choose_collectible()
            self.settings.collection[item]=self.settings.collection.get(item,0)+1
            self.found_icon=item_icon
            self.icon_until=self.tick+22
            self._set_state("happy",20)
            self.say(f"{item} 찾았다!",1900)
            self._add_adventure_log("모험",f"{item_icon} {item} 발견")
        else:
            friend=random.choice(FRIENDS)
            self.settings.fights+=1
            win_rate=min(0.75,0.42+self.settings.affection/250)
            if random.random()<win_rate:
                self.settings.wins+=1
                self._gain_exp(4)
                self._set_state("happy",24)
                self.say(f"{friend}에게 이겼어!",2300)
                self._add_adventure_log("다툼",f"{friend}에게 승리")
            else:
                self._set_state("pant",26)
                self.say(f"{friend}랑 싸우고 삐졌어…",2300)
                self._add_adventure_log("다툼",f"{friend}와 다투고 패배")
        self.settings.save()

    def feed(self):
        self._wake_from_sleep()
        self.settings.affection=min(100,self.settings.affection+5)
        self.settings.hunger=min(100,self.settings.hunger+30)
        self.settings.mood=min(100,self.settings.mood+6)
        self._gain_exp(2)
        self.settings.save()
        self._set_state("happy",24)
        self.say(f"맛있어! ♥ {self.settings.affection}")

    def play(self):
        self._wake_from_sleep()
        if self.settings.stay_sitting:
            self.settings.stay_sitting=False
            self.stay_sitting_var.set(False)
        if self.settings.energy<12:
            self.say("조금 피곤해... 먼저 쉬고 싶어 💤")
            return
        self.settings.energy=max(0,self.settings.energy-12)
        self.settings.mood=min(100,self.settings.mood+14)
        self.settings.affection=min(100,self.settings.affection+2)
        self._gain_exp(3)
        self.settings.save()
        self._set_state("run",55)
        self.ball_until=self.tick+50
        self.say("공놀이 신난다! 🎾")

    def happy(self):
        self._wake_from_sleep()
        self.settings.affection=min(100,self.settings.affection+1)
        self.settings.mood=min(100,self.settings.mood+4)
        self.settings.save()
        self._set_state("happy",22)
        self.say("헤헤, 좋아!")

    def show_status(self):
        PetInfoWindow(self.root,self.settings,"status")

    def show_collection(self):
        PetInfoWindow(self.root,self.settings,"collection")

    def show_adventure_log(self):
        self._ensure_daily_log()
        PetInfoWindow(self.root,self.settings,"log")

    def go_taskbar(self):
        self.surface_hwnd=0
        self.settings.surface_hwnd=0
        self.settings.surface_offset_y=0
        self.settings.save()
        self._snap_to_surface()
        self._set_state("happy",18)
        self.say("아래에서 놀게!")

    def reset_pet(self):
        if not messagebox.askyesno(
            "펫 초기화",
            "구름이를 처음 상태로 되돌릴까요?\n\n"
            "애정도, 포만감, 체력, 기분, 레벨/경험치, 수집품, 모험 통계와 크기가 초기화됩니다.",
            parent=self.root,
        ):
            return

        # Keep application-level preferences, but reset all pet data.
        auto_start=self.settings.auto_start
        show_speech_bubbles=self.settings.show_speech_bubbles
        follow_mouse=self.settings.follow_mouse
        stay_sitting=self.settings.stay_sitting
        defaults=Settings(
            configured=True,name="구름이",auto_start=auto_start,
            show_speech_bubbles=show_speech_bubbles,follow_mouse=follow_mouse,
            stay_sitting=stay_sitting
        )
        for field_name in Settings.__dataclass_fields__:
            setattr(self.settings,field_name,getattr(defaults,field_name))

        self.surface_hwnd=0
        self.falling=False
        self.fall_velocity=0.0
        self.bounce_count=0
        self.settings.save()
        self._load_frames()
        self._snap_to_surface()
        self._set_state("happy",24)
        self.say("다시 처음부터! 나는 구름이야 ☁️",2800)

    def _drag_start(self,event):
        self._wake_from_sleep()
        self.falling=False
        self.fall_velocity=0.0
        self.bounce_count=0
        self.drag_origin=self.surface.cursor_position()
        self.position_origin=(self.root.winfo_x(),self.root.winfo_y())

    def _drag_move(self,event):
        if not self.drag_origin:
            return
        cursor_x,cursor_y=self.surface.cursor_position()
        dx=cursor_x-self.drag_origin[0]
        dy=cursor_y-self.drag_origin[1]
        left,right,_ground=self.surface.virtual_bounds_and_ground(
            self.position_origin[0]+dx+self.width//2,
            self.position_origin[1]+dy+self.height//2
        )
        x=max(left,min(right-self.width,self.position_origin[0]+dx))
        _left,_right,ground=self.surface.virtual_bounds_and_ground(
            x+self.width//2,
            self.position_origin[1]+dy+self.height//2
        )
        top=min((area[1] for area in self.surface.monitor_work_areas()),default=0)
        y=max(top,min(ground-self.height,self.position_origin[1]+dy))
        self._place(x,y)

    def _drag_end(self,event):
        moved=False
        if self.position_origin:
            moved=(
                abs(self.root.winfo_x()-self.position_origin[0])>3 or
                abs(self.root.winfo_y()-self.position_origin[1])>3
            )
        self.drag_origin=None
        self.position_origin=None

        # A manual move takes priority over cursor-following; otherwise follow mode
        # would immediately pull a pet placed on an app back to the taskbar.
        if moved and self.settings.follow_mouse:
            self.settings.follow_mouse=False
            self.follow_mouse_var.set(False)

        self.surface_hwnd=0
        self.settings.surface_hwnd=0
        self.settings.surface_offset_y=0

        x=self.root.winfo_x()
        foot_y=self.root.winfo_y()+self.height
        hit=self.surface.falling_surface(x,x+self.width,foot_y-24,foot_y+24)
        if hit:
            ground,hwnd,surface=hit
            left,right,_ground=surface
            self.surface_hwnd=hwnd
            self.settings.surface_hwnd=hwnd
            x=max(left,min(right-self.width,x))
            self.falling=False
            self.fall_velocity=0.0
            self.bounce_count=0
            self._place(x,ground-self.height)
            self._set_state("idle",random.randint(25,50))
            self.settings.save()
            self.say("여기서 놀게!",1400)
            return

        # Only fall when there really is no window surface at the release point.
        self.falling=True
        self.fall_velocity=0.0
        self.bounce_count=0
        self._set_state("front",10**6)
        self.settings.save()
        self.say("아래에 뭐가 있나 볼까?",1400)

    def _show_menu(self,event):
        self.menu.tk_popup(event.x_root,event.y_root)

    def open_setup(self):
        dialog=SetupWindow(self.root,self.settings)
        self.root.wait_window(dialog)
        if dialog.result:
            self._load_frames()
            self._snap_to_surface()
            self.say("새 크기 어때?")

    def _save_position(self):
        self.settings.x=self.root.winfo_x()
        self.settings.surface_hwnd=self.surface_hwnd
        self.settings.save()

    def close(self):
        self._save_position()
        self.root.destroy()

def main():
    enable_dpi_awareness()
    root=tk.Tk()
    root.withdraw()
    settings=Settings.load()
    if not settings.configured:
        setup=SetupWindow(root,settings,first_run=True)
        root.wait_window(setup)
        if not setup.result:
            root.destroy()
            return
    root.deiconify()
    DogWindow(root,settings)
    root.mainloop()

if __name__=="__main__":
    main()
